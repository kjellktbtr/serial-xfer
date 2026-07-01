; SPDX-License-Identifier: GPL-2.0-only
; Copyright (C) 2026 Kjell Kristian Grane Torgersen
;
; xfercom.asm — hand-written NASM DOS .COM serial file-transfer agent.
;
; Builds a flat 16-bit COM (org 0x100) that needs no runtime/link step:
;   nasm -f bin xfercom.asm -o XFER.COM
;
; Usage: XFER [baud [com]]
;   baud — any integer N such that 115200/N is an integer, range 2..115200
;           (e.g. 300, 1200, 9600, 19200, 38400, 57600, 115200); default 9600
;   com  — COM port number 1..4; default 1
; If one argument is given it is the baud rate; COM1 is assumed.
; It reproduces the behaviour of xfer.c (the pyc-compiled agent): the same
; COBS framing, per-packet CRC-16/CCITT, whole-file CRC-32 (zlib 0xEDB88320),
; ACK pacing, and the OPEN/DATA/CLOSE/GET/MKDIR/LIST/QUIT command set, talking
; to host.py over a configurable COM port at a configurable baud rate (default
; COM1, 9600 baud, 8N1).  The DOS/UART primitives that xfer.c
; pulled from stdlib (uart_*, POSIX file I/O, find_first/next, mkdir, puts) are
; inlined here as INT 14h/21h and direct UART port I/O.
;
; Internal calling convention (not cdecl): arguments in registers, documented
; per routine; every helper preserves all registers except its result (AX, or
; DX:AX for crc32), so callers can keep state in registers across calls.

cpu 8086        ; 8086/8088-clean (no 186/286/386 instructions) — runs on a
                ; vintage PC with DOS 2.0+; NASM enforces the instruction level.
bits 16
org 0x100

; COM port base addresses are stored at runtime in v_base (set by parse_args).
; Default: COM1 = 0x3F8.  Table: com_tbl dw 0x3F8,0x2F8,0x3E8,0x2E8.
%define CHUNK     128

%define T_OPEN    1
%define T_DATA    2
%define T_CLOSE   3
%define T_QUIT    4
%define T_GET     5
%define T_MKDIR   6
%define T_LIST    7
%define T_ENTRY   8
%define T_MSG     9
%define T_DEL     10                ; v2: delete file
%define T_RMD     11                ; v2: remove dir
%define T_REN     12                ; v2: rename old\0new
%define T_PREAD   13                ; v2: ranged read  (offset4 len2 name)
%define T_PWRITE  14                ; v2: ranged write (offset4 name\0 bytes)
%define T_RAW     15                ; v2: print DATA verbatim (no added CRLF)
%define T_VERSION 16                ; v3: query protocol version; ACK replies with version byte
%define T_ACK     0x10
%define T_NAK     0x11

%define FA_DIREC  0x10
%define DTA_ATTR  21
%define DTA_TIME  22                ; word: packed time (bits 15-11 h, 10-5 min, 4-0 s/2)
%define DTA_DATE  24                ; word: packed date (bits 15-9 year-1980, 8-5 m, 4-0 d)
%define DTA_SIZE  26
%define DTA_NAME  30

; ---------------------------------------------------------------------------
; Entry / main loop  (mirrors main() in xfer.c:215)
; ---------------------------------------------------------------------------
start:
    call parse_args              ; sets v_base, v_div, v_com, v_baudstr
    call uart_init
    mov word [v_fd], -1
    mov word [v_wcrc], 0
    mov word [v_wcrc+2], 0
    ; Banner: "xfer ready on COMn at NNNN baud - press Q to quit"
    mov si, msg_rdyA             ; "xfer ready on COM"
    call putstr
    mov ah, 0x02
    mov dl, '0'
    add dl, [v_com]
    int 0x21
    mov si, msg_rdyB             ; " at "
    call putstr
    mov si, [v_baudstr]          ; asciiz baud digits
    call putstr
    mov si, msg_rdyC             ; " baud - press Q to quit"
    call puts                    ; adds CRLF

.main_loop:
    call read_frame             ; AX = n (decoded packet length in pk[])
    cmp ax, 4
    jl .main_loop               ; if (n < 4) continue;
    mov [v_n], ax

    ; got = (pk[n-2] << 8) | pk[n-1]
    mov si, pk
    add si, ax                  ; si = pk + n
    mov dh, [si-2]              ; high byte
    mov dl, [si-1]              ; low byte
    mov [v_got16], dx

    ; calc = crc16(pk, n-2)
    mov si, pk
    mov cx, [v_n]
    sub cx, 2
    call crc16                  ; AX = calc

    mov bl, [pk]
    mov [v_type], bl            ; type = pk[0]
    mov bl, [pk+1]
    mov [v_seq], bl             ; seq  = pk[1]
    mov cx, [v_n]
    sub cx, 4
    mov [v_dlen], cx            ; dlen = n - 4

    cmp ax, [v_got16]
    je .crc_ok
    ; bad CRC -> NAK and resync
    mov bl, T_NAK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
    jmp .main_loop

.crc_ok:
    mov al, [v_type]
    cmp al, T_OPEN
    je .h_open
    cmp al, T_DATA
    je .h_data
    cmp al, T_CLOSE
    je .h_close
    cmp al, T_GET
    je .h_get
    cmp al, T_LIST
    je .h_list
    cmp al, T_MKDIR
    je .h_mkdir
    cmp al, T_MSG
    je .h_msg
    cmp al, T_DEL
    je .h_del
    cmp al, T_RMD
    je .h_rmd
    cmp al, T_REN
    je .h_ren
    cmp al, T_PREAD
    je .h_pread
    cmp al, T_PWRITE
    je .h_pwrite
    cmp al, T_RAW
    je .h_raw
    cmp al, T_QUIT
    je .h_quit_ack
    cmp al, T_VERSION
    je .h_version
    ; default: ACK
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
    jmp .main_loop

; --- OPEN (xfer.c:235) ---
.h_open:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0          ; pk[2+dlen] = 0  (NUL-terminate name)
    cmp word [v_fd], 0
    jl .ho_noclose
    mov bx, [v_fd]
    call do_close
.ho_noclose:
    mov dx, pk+2
    mov bx, 0x0301              ; O_WRONLY|O_CREAT|O_TRUNC
    call do_open
    mov [v_fd], ax
    mov word [v_wcrc], 0
    mov word [v_wcrc+2], 0
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
    jmp .main_loop

; --- DATA (xfer.c:242) ---
.h_data:
    cmp word [v_fd], 0
    jl .hd_nowrite
    mov bx, [v_fd]
    mov dx, pk+2
    mov cx, [v_dlen]
    call do_write
.hd_nowrite:
    mov si, pk+2
    mov cx, [v_dlen]
    mov ax, [v_wcrc]
    mov dx, [v_wcrc+2]
    call crc32                  ; DX:AX = updated wcrc
    mov [v_wcrc], ax
    mov [v_wcrc+2], dx
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
    jmp .main_loop

; --- CLOSE (xfer.c:246): compare expected CRC-32 (big-endian) to wcrc ---
.h_close:
    mov byte [v_status], 1
    mov cx, [v_dlen]
    cmp cx, 4
    jl .hc_setstatus
    mov al, [pk+2]
    cmp al, [v_wcrc+3]         ; (wcrc >> 24) & 0xFF
    jne .hc_setstatus
    mov al, [pk+3]
    cmp al, [v_wcrc+2]         ; (wcrc >> 16) & 0xFF
    jne .hc_setstatus
    mov al, [pk+4]
    cmp al, [v_wcrc+1]         ; (wcrc >> 8) & 0xFF
    jne .hc_setstatus
    mov al, [pk+5]
    cmp al, [v_wcrc]           ; wcrc & 0xFF
    jne .hc_setstatus
    mov byte [v_status], 0
.hc_setstatus:
    ; Extract time/date if present (dlen >= 8 = v1 extended CLOSE from host)
    mov word [v_ftime], 0
    mov word [v_ftime+2], 0
    cmp word [v_dlen], 8
    jl .hc_notime
    mov ax, [pk+6]             ; time LE (DATA byte 4-5)
    mov [v_ftime], ax
    mov ax, [pk+8]             ; date LE (DATA byte 6-7)
    mov [v_ftime+2], ax
.hc_notime:
    cmp word [v_fd], 0
    jl .hc_nofd
    mov bx, [v_fd]
    ; set date/time on open handle before closing (only if non-zero)
    mov cx, [v_ftime]
    mov dx, [v_ftime+2]
    test cx, cx
    jnz .hc_setft
    test dx, dx
    jz .hc_doclose
.hc_setft:
    call do_setftime            ; BX=handle, CX=packed time, DX=packed date
.hc_doclose:
    call do_close
    mov word [v_fd], -1
.hc_nofd:
    mov al, [v_status]
    mov [eb], al
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, eb
    mov cx, 1
    call send_packet
    jmp .main_loop

; --- GET (xfer.c:259) ---
.h_get:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0
    mov si, pk+2
    mov al, [v_seq]
    call serve_get
    jmp .main_loop

; --- LIST (xfer.c:262) ---
.h_list:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0
    mov si, pk+2
    mov al, [v_seq]
    call serve_list
    jmp .main_loop

; --- MKDIR (xfer.c:265) ---
.h_mkdir:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0
    mov dx, pk+2
    call do_mkdir
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
    jmp .main_loop

; --- MSG (host->dos): display the text on the target screen, then ACK ---
.h_msg:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0          ; NUL-terminate the message text
    mov si, pk+2
    call puts
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
    jmp .main_loop

; --- RAW (host->dos): print DATA verbatim (no added CRLF), then ACK.  Lets the
; host own line endings (e.g. a trailing CR to overwrite a status line). ---
.h_raw:
    mov cx, [v_dlen]
    mov si, pk+2
    jcxz .hraw_ack
.hraw_loop:
    mov dl, [si]
    mov ah, 0x02
    int 0x21
    inc si
    loop .hraw_loop
.hraw_ack:
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
    jmp .main_loop

; --- VERSION (T_VERSION=16): reply ACK with 1-byte protocol version (0x01).
; An old agent without this handler falls through to the default empty-ACK above,
; which the host interprets as protocol version 0 (no date/time support). ---
.h_version:
    mov byte [eb], 1            ; protocol version 1
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, eb
    mov cx, 1
    call send_packet
    jmp .main_loop

; ===========================================================================
; Protocol v2 handlers (all reply with an ACK; base types above stay frozen)
; ===========================================================================

; --- DEL (delete file) ---
.h_del:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0          ; NUL-terminate name
    mov dx, pk+2
    call do_delete              ; AX = 0 ok / -1 err
    jmp .v2_ack_ax

; --- RMD (remove directory) ---
.h_rmd:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0
    mov dx, pk+2
    call do_rmdir
    jmp .v2_ack_ax

; --- REN (rename): DATA = old \0 new ---
.h_ren:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0          ; terminate the 'new' string
    mov si, pk+2                ; scan past 'old' to find 'new'
.hr_scan:
    lodsb
    test al, al
    jnz .hr_scan
    mov dx, pk+2                ; DS:DX = old
    mov di, si                  ; ES:DI = new (ES set to DS inside do_rename)
    call do_rename
    jmp .v2_ack_ax

; Shared tail: AX (0 ok / nonzero err) -> ACK with a 1-byte status (0/1).
.v2_ack_ax:
    mov byte [eb], 0
    test ax, ax
    jz .v2_ack_send
    mov byte [eb], 1
.v2_ack_send:
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, eb
    mov cx, 1
    call send_packet
    jmp .main_loop

; --- PREAD: DATA = offset(4 LE) length(2 LE) name ; reply ACK(seq, bytes) ---
.h_pread:
    mov bx, [v_dlen]
    mov si, pk
    add si, bx
    mov byte [si+2], 0          ; NUL-terminate name
    mov dx, pk+8                ; name
    xor bx, bx                  ; O_RDONLY
    call do_open
    cmp ax, 0
    jl .hpr_empty               ; open failed -> empty reply
    mov [v_rfd], ax
    mov bx, ax                  ; lseek SEEK_SET to offset
    mov dx, [pk+2]             ; offset low word
    mov cx, [pk+4]             ; offset high word
    call do_lseek
    mov cx, [pk+6]            ; length
    cmp cx, CHUNK
    jbe .hpr_rd
    mov cx, CHUNK              ; cap to fbuf size
.hpr_rd:
    mov bx, [v_rfd]
    mov dx, fbuf
    call do_read                ; AX = bytes or -1
    cmp ax, 0
    jge .hpr_have
    xor ax, ax                  ; error -> 0 bytes
.hpr_have:
    mov [v_got], ax
    mov bx, [v_rfd]
    call do_close
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, fbuf
    mov cx, [v_got]
    call send_packet
    jmp .main_loop
.hpr_empty:
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, fbuf
    xor cx, cx
    call send_packet
    jmp .main_loop

; --- PWRITE: DATA = offset(4 LE) name \0 bytes ; CX=0 write -> truncate/create ---
.h_pwrite:
    mov si, pk+6                ; scan past name to the bytes
.hpw_scan:
    lodsb
    test al, al
    jnz .hpw_scan
    mov ax, pk+2
    add ax, [v_dlen]           ; ax = end of DATA
    sub ax, si                  ; ax = byte count after the name
    mov [v_got], ax
    mov [v_name], si            ; bytes pointer
    mov dx, pk+6                ; open existing read/write
    mov bx, 2                   ; O_RDWR (no O_CREAT)
    call do_open
    cmp ax, 0
    jge .hpw_open
    mov dx, pk+6                ; missing -> create empty
    mov bx, 0x0301             ; O_WRONLY|O_CREAT|O_TRUNC
    call do_open
    cmp ax, 0
    jl .hpw_err
.hpw_open:
    mov [v_rfd], ax
    mov bx, ax
    mov dx, [pk+2]
    mov cx, [pk+4]
    call do_lseek
    mov bx, [v_rfd]
    mov dx, [v_name]
    mov cx, [v_got]            ; may be 0 -> sets EOF here (truncate)
    call do_write
    mov bx, [v_rfd]
    call do_close
    xor ax, ax
    jmp .v2_ack_ax
.hpw_err:
    mov ax, -1
    jmp .v2_ack_ax

; --- QUIT / clean exit (also reached by keyboard 'Q' and mid-stream QUIT) ---
; On a host T_QUIT we first ACK so the host's quit() sees it; keyboard/midstream
; callers jump straight in.  Either way: close any open file, then exit(0).
.h_quit_ack:
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, pk
    xor cx, cx
    call send_packet
do_quit:
    cmp word [v_fd], 0
    jl .dq_exit
    mov bx, [v_fd]
    call do_close
    mov word [v_fd], -1
.dq_exit:
    mov ax, 0x4C00             ; exit(0)
    int 0x21

; ===========================================================================
; Helpers
; ===========================================================================

; crc16(SI=ptr, CX=n) -> AX=crc.  CCITT poly 0x1021, init 0xFFFF (xfer.c:51).
; Preserves SI, CX, BX.
crc16:
    push bx
    push cx
    push si
    mov ax, 0xFFFF
    jcxz .done
.byte:
    mov bl, [si]
    inc si
    mov bh, bl
    xor bl, bl
    xor ax, bx                  ; crc ^= d[i] << 8
    push cx
    mov cx, 8
.bit:
    test ax, 0x8000
    jz .no
    shl ax, 1
    xor ax, 0x1021
    jmp .next
.no:
    shl ax, 1
.next:
    loop .bit
    pop cx
    loop .byte
.done:
    pop si
    pop cx
    pop bx
    ret

; crc32(SI=ptr, CX=n, DX:AX=crc) -> DX:AX=crc.  Reflected 0xEDB88320, zlib
; chaining (xfer.c:68).  Preserves SI, CX, BX, DI.
crc32:
    push si
    push cx
    push bx
    push di
    not ax
    not dx                      ; crc ^= 0xFFFFFFFF
    jcxz .done
.byte:
    mov bl, [si]
    inc si
    xor al, bl                  ; crc ^= d[i]
    mov di, 8
.bit:
    test al, 1
    jz .shift
    shr dx, 1
    rcr ax, 1                   ; crc >>= 1
    xor dx, 0xEDB8
    xor ax, 0x8320              ; ^= 0xEDB88320
    jmp .nextbit
.shift:
    shr dx, 1
    rcr ax, 1
.nextbit:
    dec di
    jnz .bit
    loop .byte
.done:
    not ax
    not dx                      ; crc ^= 0xFFFFFFFF
    pop di
    pop bx
    pop cx
    pop si
    ret

; cobs_decode(SI=in, CX=len, DI=out) -> AX=decoded length (xfer.c:83).
; Preserves SI, DI, BX, CX, DX.
cobs_decode:
    push si
    push di
    push bx
    push cx
    push dx
    mov bx, si
    add bx, cx                  ; bx = end of input
    mov dx, di                  ; dx = out start
.while:
    cmp si, bx
    jae .done
    mov al, [si]                ; code
    inc si
    mov ah, al                  ; remember code
    mov cl, al
    xor ch, ch
    dec cx                      ; cx = code - 1
    jcxz .after
.copy:
    cmp si, bx
    jae .after
    mov al, [si]
    inc si
    mov [di], al
    inc di
    loop .copy
.after:
    cmp ah, 0xFF
    je .while
    cmp si, bx
    jae .while
    mov byte [di], 0           ; insert delimiter zero
    inc di
    jmp .while
.done:
    mov ax, di
    sub ax, dx                  ; wp = di - out_start
    pop dx
    pop cx
    pop bx
    pop di
    pop si
    ret

; cobs_encode(SI=in, CX=len, DI=out) -> AX=encoded length (xfer.c:95).
; Preserves SI, DI, BX, BP, CX, DX.
cobs_encode:
    push si
    push di
    push bx
    push bp
    push cx
    push dx
    mov bx, di                  ; codep pointer = out+0
    lea bp, [di+1]              ; wp pointer    = out+1
    mov dl, 1                   ; code = 1
    jcxz .flush
.loop:
    mov al, [si]
    inc si
    test al, al
    jnz .nonzero
    mov [bx], dl                ; out[codep] = code
    mov bx, bp                  ; codep = wp
    inc bp                      ; wp++
    mov dl, 1                   ; code = 1
    jmp .next
.nonzero:
    mov [bp], al                ; out[wp++] = in[i]
    inc bp
    inc dl                      ; code++
    cmp dl, 0xFF
    jne .next
    mov [bx], dl                ; out[codep] = 0xFF
    mov bx, bp
    inc bp
    mov dl, 1
.next:
    loop .loop
.flush:
    mov [bx], dl                ; out[codep] = code
    mov ax, bp
    sub ax, di                  ; wp = bp - out_start
    pop dx
    pop cx
    pop bp
    pop bx
    pop di
    pop si
    ret

; read_frame() -> AX = decoded length (into pk[]) (xfer.c:116).
; Reads UART bytes until a 0x00 delimiter, then COBS-decodes.
read_frame:
    push si
    push di
    push cx
    push bx
    mov di, rxf
    xor cx, cx                  ; n = 0
.rf_read:
    call uart_getc              ; AL = byte
    test al, al
    jz .rf_eof                  ; 0x00 ends the frame
    cmp cx, 600
    jae .rf_read                ; drop overflow but keep reading
    mov [di], al
    inc di
    inc cx
    jmp .rf_read
.rf_eof:
    mov si, rxf                 ; cobs_decode(rxf, n, pk)
    mov di, pk
    call cobs_decode            ; AX = length
    pop bx
    pop cx
    pop di
    pop si
    ret

; send_packet(BL=type, BH=seq, SI=data, CX=dlen) (xfer.c:126).
; Builds op[], appends CRC-16 big-endian, COBS-encodes into tx[], emits + 0x00.
send_packet:
    push ax                     ; save the regs we clobber (8086 has no PUSHA)
    push bx
    push cx
    push dx
    push si
    push di
    mov di, op
    mov [di], bl                ; op[0] = type
    mov [di+1], bh              ; op[1] = seq
    lea di, [op+2]
    jcxz .nocopy
.copy:
    mov al, [si]
    inc si
    mov [di], al
    inc di
    loop .copy
.nocopy:
    ; plen = 2 + dlen.  Recover it from di: di = op + 2 + dlen.
    mov dx, di
    sub dx, op                  ; dx = plen = 2 + dlen
    push dx
    mov si, op
    mov cx, dx
    call crc16                  ; AX = crc
    pop dx
    mov di, op
    add di, dx                  ; di = op + plen
    mov [di], ah                ; CRC high
    mov [di+1], al              ; CRC low
    add dx, 2                   ; plen += 2
    mov si, op
    mov cx, dx
    mov di, tx
    call cobs_encode            ; AX = elen
    mov cx, ax
    mov si, tx
    jcxz .send0
.send:
    mov al, [si]
    inc si
    call uart_putc
    loop .send
.send0:
    xor al, al
    call uart_putc              ; frame delimiter
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; wait_ack() -> AX = 1 if the next frame is an ACK (xfer.c:143).  Paces streams.
wait_ack:
    call read_frame             ; AX = n
    cmp ax, 4
    jl .no
    mov al, [pk]
    cmp al, T_QUIT
    je do_quit                  ; honour QUIT even mid-stream -> clean exit
    cmp al, T_ACK
    jne .no
    mov ax, 1
    ret
.no:
    xor ax, ax
    ret

; crc_to_be(DX:AX = crc) -> packs big-endian into eb[0..3] (xfer.c:151).
crc_to_be:
    mov [eb+0], dh
    mov [eb+1], dl
    mov [eb+2], ah
    mov [eb+3], al
    ret

; serve_get(SI=name, AL=seq) (xfer.c:160).
serve_get:
    mov [v_seq], al
    mov [v_name], si
    mov dx, si
    xor bx, bx                  ; O_RDONLY
    call do_open
    mov [v_rfd], ax
    ; ACK the GET
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, op
    xor cx, cx
    call send_packet
    cmp word [v_rfd], 0
    jge .have
    ; missing file: CLOSE with crc 0
    xor dx, dx
    xor ax, ax
    call crc_to_be
    mov bl, T_CLOSE
    mov bh, 0
    mov si, eb
    mov cx, 4
    call send_packet
    call wait_ack
    ret
.have:
    mov word [v_rcrc], 0
    mov word [v_rcrc+2], 0
    mov byte [v_dseq], 0
.loop:
    mov bx, [v_rfd]
    mov dx, fbuf
    mov cx, CHUNK
    call do_read                ; AX = bytes (<=0 ends)
    cmp ax, 0
    jle .eof
    mov [v_got], ax
    mov si, fbuf
    mov cx, ax
    mov ax, [v_rcrc]
    mov dx, [v_rcrc+2]
    call crc32
    mov [v_rcrc], ax
    mov [v_rcrc+2], dx
    mov bl, T_DATA
    mov bh, [v_dseq]
    mov si, fbuf
    mov cx, [v_got]
    call send_packet
    call wait_ack
    inc byte [v_dseq]           ; (dseq + 1) & 0xFF, byte wraps
    jmp .loop
.eof:
    mov bx, [v_rfd]
    call do_getftime            ; CX=packed time, DX=packed date (must be before close)
    mov [v_ftime], cx
    mov [v_ftime+2], dx
    call do_close
    mov ax, [v_rcrc]
    mov dx, [v_rcrc+2]
    call crc_to_be              ; fills eb+0..3 with CRC-32 big-endian
    mov ax, [v_ftime]
    mov [eb+4], al
    mov [eb+5], ah              ; time LE at eb+4..5
    mov ax, [v_ftime+2]
    mov [eb+6], al
    mov [eb+7], ah              ; date LE at eb+6..7
    mov bl, T_CLOSE
    mov bh, [v_dseq]
    mov si, eb
    mov cx, 8                   ; crc32(4) + time(2) + date(2)
    call send_packet
    call wait_ack
    ret

; serve_list(SI=spec, AL=seq) (xfer.c:190).
serve_list:
    mov [v_seq], al
    mov [v_name], si
    mov bl, T_ACK
    mov bh, [v_seq]
    mov si, op
    xor cx, cx
    call send_packet
    mov dx, dta
    call do_setdta
    mov dx, [v_name]
    mov cx, FA_DIREC
    call do_findfirst           ; AX = 0 found / -1
.loop:
    cmp ax, 0
    jne .end
    mov al, [dta+DTA_ATTR]
    mov [eb+0], al
    mov al, [dta+DTA_SIZE]
    mov [eb+1], al
    mov al, [dta+DTA_SIZE+1]
    mov [eb+2], al
    mov al, [dta+DTA_SIZE+2]
    mov [eb+3], al
    mov al, [dta+DTA_SIZE+3]
    mov [eb+4], al
    mov al, [dta+DTA_TIME]      ; packed time LE (2 bytes at DTA+22)
    mov [eb+5], al
    mov al, [dta+DTA_TIME+1]
    mov [eb+6], al
    mov al, [dta+DTA_DATE]      ; packed date LE (2 bytes at DTA+24)
    mov [eb+7], al
    mov al, [dta+DTA_DATE+1]
    mov [eb+8], al
    mov si, dta+DTA_NAME
    mov di, eb+9
    xor cx, cx
.name:
    cmp cx, 14
    jae .namedone
    mov al, [si]
    test al, al
    jz .namedone
    mov [di], al
    inc si
    inc di
    inc cx
    jmp .name
.namedone:
    add cx, 9                   ; alen = 9 + i (attr + size + time + date + name)
    mov bl, T_ENTRY
    mov bh, 0
    mov si, eb
    call send_packet
    call wait_ack
    call do_findnext            ; AX = 0 / -1
    jmp .loop
.end:
    mov bl, T_CLOSE
    mov bh, 0
    mov si, op
    xor cx, cx
    call send_packet
    call wait_ack
    ret

; ---------------------------------------------------------------------------
; Inlined runtime primitives (UART port I/O + DOS INT 21h)
; ---------------------------------------------------------------------------

; ---------------------------------------------------------------------------
; parse_args — read PSP command tail, populate v_base/v_div/v_com/v_baudstr.
;
; Syntax: XFER [baud [com]]
;   If 0 args: defaults (9600, COM1).
;   If 1 arg:  baud rate; COM1.
;   If 2 args: baud rate, then COM number.
;   Bad input: print usage and exit.
;
; Clobbers: AX, BX, CX, DX, SI, DI (called only from start: before any state).
; ---------------------------------------------------------------------------
parse_args:
    ; --- install defaults ---
    mov word [v_base], 0x3F8
    mov word [v_div],  12        ; 115200 / 12 = 9600
    mov byte [v_com],  1
    mov word [v_baudstr], msg_9600

    ; --- scan PSP command tail (org 0x100: DS = PSP segment) ---
    mov si, 0x81                 ; tail starts here; [0x80] = length byte

.pa_skip1:                       ; skip leading spaces / tabs
    mov al, [si]
    cmp al, 0x0D
    je .pa_done                  ; CR → no args
    cmp al, ' '
    je .pa_skip1x
    cmp al, 0x09
    je .pa_skip1x
    jmp .pa_baud_start
.pa_skip1x:
    inc si
    jmp .pa_skip1

.pa_baud_start:
    ; First non-space must be a digit.
    mov al, [si]
    cmp al, '0'
    jb .pa_err
    cmp al, '9'
    ja .pa_err

    ; Init 32-bit baud accumulator and copy-buffer pointer.
    mov word [v_baud32],   0
    mov word [v_baud32+2], 0
    mov di, v_baudstr_buf        ; copy digits here for the banner

.pa_baud_digit:
    mov al, [si]
    cmp al, '0'
    jb .pa_baud_end
    cmp al, '9'
    ja .pa_baud_end
    ; Store in banner buffer.
    mov [di], al
    inc di
    ; acc = acc * 10 (32-bit: low_word then high_word, carrying).
    mov ax, [v_baud32]
    mov cx, 10
    mul cx                       ; DX:AX = low * 10
    mov bx, dx                   ; bx = carry into high word
    mov [v_baud32], ax
    mov ax, [v_baud32+2]
    mul cx                       ; DX:AX = high * 10 (DX==0 for our range)
    add ax, bx
    mov [v_baud32+2], ax
    ; acc += digit
    mov al, [si]
    sub al, '0'
    xor ah, ah
    add [v_baud32], ax
    adc word [v_baud32+2], 0
    inc si
    jmp .pa_baud_digit

.pa_baud_end:
    mov byte [di], 0             ; NUL-terminate banner buffer
    mov word [v_baudstr], v_baudstr_buf

    ; --- validate baud: 2 <= baud <= 115200 ---
    mov ax, [v_baud32+2]         ; high word
    test ax, ax
    jnz .pa_baud_hi

    ; high == 0: check low >= 2
    mov ax, [v_baud32]           ; low word
    cmp ax, 2
    jb .pa_err
    ; divisor = 115200 / baud  (115200 = 0x1C200)
    mov dx, 1
    mov ax, 0xC200               ; DX:AX = 115200
    div word [v_baud32]          ; AX = divisor (fits: 115200/2 = 57600 <= 65535)
    mov [v_div], ax
    jmp .pa_baud_ok

.pa_baud_hi:
    ; high != 0: only accept exactly 115200 (high=1, low=0xC200)
    cmp ax, 1
    jne .pa_err
    mov ax, [v_baud32]
    cmp ax, 0xC200
    jne .pa_err
    mov word [v_div], 1          ; divisor = 1 → 115200 baud

.pa_baud_ok:
    ; --- look for COM arg: skip spaces after baud ---
.pa_skip2:
    mov al, [si]
    cmp al, 0x0D
    je .pa_done                  ; CR → done, use defaults for COM
    cmp al, ' '
    je .pa_skip2x
    cmp al, 0x09
    je .pa_skip2x
    jmp .pa_com_start
.pa_skip2x:
    inc si
    jmp .pa_skip2

.pa_com_start:
    ; Must be a single digit 1..4 followed immediately by end/space.
    mov al, [si]
    cmp al, '0'
    jb .pa_err
    cmp al, '9'
    ja .pa_err
    sub al, '0'
    mov [v_com], al
    inc si
    ; Next char must be end-of-line, space, or tab (no multi-digit COM).
    mov al, [si]
    cmp al, 0x0D
    je .pa_com_ok
    cmp al, ' '
    je .pa_trail
    cmp al, 0x09
    je .pa_trail
    jmp .pa_err                  ; digit or garbage after COM number

.pa_trail:                       ; skip trailing spaces; any non-space is an error
    inc si
.pa_trail_lp:
    mov al, [si]
    cmp al, 0x0D
    je .pa_com_ok
    cmp al, ' '
    je .pa_trail_lp_x
    cmp al, 0x09
    je .pa_trail_lp_x
    jmp .pa_err                  ; trailing garbage
.pa_trail_lp_x:
    inc si
    jmp .pa_trail_lp

.pa_com_ok:
    ; Validate COM number 1..4.
    mov al, [v_com]
    cmp al, 1
    jb .pa_err
    cmp al, 4
    ja .pa_err
    ; Map to base address: index = (com - 1) * 2, look up in com_tbl.
    dec al
    xor ah, ah
    shl ax, 1                    ; *2 (word index); shl r16,1 is 8086-legal
    mov bx, com_tbl
    add bx, ax
    mov ax, [bx]
    mov [v_base], ax

.pa_done:
    ret

.pa_err:
    mov si, msg_usage
    call puts
    mov ax, 0x4C01
    int 0x21                     ; exit(1)

; ---------------------------------------------------------------------------
; uart_init() — 8N1, runtime baud (v_div) and port (v_base), FIFOs on, IRQs off.
uart_init:
    push ax
    push bx
    push dx
    mov bx, [v_base]
    lea dx, [bx+1]
    xor al, al
    out dx, al                  ; IER = 0  (interrupts off)
    lea dx, [bx+3]
    mov al, 0x80
    out dx, al                  ; LCR: set DLAB to access divisor latches
    mov dx, bx
    mov ax, [v_div]             ; AL = DLL (low byte), AH = DLM (high byte)
    out dx, al                  ; DLL
    lea dx, [bx+1]
    mov al, ah
    out dx, al                  ; DLM
    lea dx, [bx+3]
    mov al, 0x03
    out dx, al                  ; LCR: 8N1, clear DLAB
    lea dx, [bx+2]
    mov al, 0xC7
    out dx, al                  ; FCR: enable + clear FIFOs
    lea dx, [bx+4]
    mov al, 0x0B
    out dx, al                  ; MCR: DTR, RTS, OUT2
    pop dx
    pop bx
    pop ax
    ret

; uart_getc() -> AL = byte (AH=0).  Blocks until RX data ready, but while waiting
; also polls the BIOS keyboard so the operator can always abort with 'Q' — this
; is the universal escape from any wedged state (serial.asm:83).
uart_getc:
    push dx
    push bx
    mov bx, [v_base]
.wait:
    mov ah, 0x01                ; INT 16h: peek keystroke (ZF=1 -> none)
    int 0x16
    jz .nokey
    mov ah, 0x00                ; consume the waiting key
    int 0x16
    cmp al, 'q'
    je do_quit
    cmp al, 'Q'
    je do_quit                  ; 'Q' -> clean exit, no stack unwind needed
.nokey:
    lea dx, [bx+5]
    in al, dx                   ; LSR
    test al, 1                  ; data ready?
    jz .wait
    mov dx, bx
    in al, dx                   ; RBR
    xor ah, ah
    pop bx
    pop dx
    ret

; uart_putc(AL=byte) — blocks until THR empty, then sends (serial.asm:102).
uart_putc:
    push ax
    push cx
    push dx
    push bx
    mov cl, al                  ; save byte in CL (BX needed for port base)
    mov bx, [v_base]
.wait:
    lea dx, [bx+5]
    in al, dx                   ; LSR
    test al, 0x20               ; THR empty?
    jz .wait
    mov dx, bx
    mov al, cl
    out dx, al
    pop bx
    pop dx
    pop cx
    pop ax
    ret

; do_open(DX=path, BX=flags) -> AX=handle or -1 (posix_io.asm:33).
do_open:
    push cx
    test bx, 0x0100             ; O_CREAT?
    jz .existing
    xor cx, cx
    mov ah, 0x3C               ; create/truncate
    int 0x21
    jc .err
    jmp .out
.existing:
    mov ax, bx
    and al, 0x03               ; access mode
    mov ah, 0x3D
    int 0x21
    jc .err
.out:
    pop cx
    ret
.err:
    mov ax, -1
    pop cx
    ret

; do_close(BX=handle) (posix_io.asm:80).
do_close:
    mov ah, 0x3E
    int 0x21
    ret

; do_read(BX=handle, DX=buf, CX=count) -> AX=bytes or -1 (posix_io.asm:103).
do_read:
    mov ah, 0x3F
    int 0x21
    jc .err
    ret
.err:
    mov ax, -1
    ret

; do_write(BX=handle, DX=buf, CX=count) -> AX=bytes or -1 (posix_io.asm:128).
do_write:
    mov ah, 0x40
    int 0x21
    jc .err
    ret
.err:
    mov ax, -1
    ret

; do_mkdir(DX=path) -> AX (0 on success or "already exists") (dos_dir.asm:27).
do_mkdir:
    mov ah, 0x39
    int 0x21
    jnc .ok
    cmp ax, 5                   ; access denied ~= already exists
    je .ok
    mov ax, -1
    ret
.ok:
    xor ax, ax
    ret

; do_setdta(DX=dta) (dos_dir.asm:50).
do_setdta:
    mov ah, 0x1A
    int 0x21
    ret

; do_findfirst(DX=spec, CX=attr) -> AX=0/-1 (dos_dir.asm:62).
do_findfirst:
    mov ah, 0x4E
    int 0x21
    jc .err
    xor ax, ax
    ret
.err:
    mov ax, -1
    ret

; do_findnext() -> AX=0/-1 (dos_dir.asm:84).
do_findnext:
    mov ah, 0x4F
    int 0x21
    jc .err
    xor ax, ax
    ret
.err:
    mov ax, -1
    ret

; --- v2 INT 21h helpers ---

; do_lseek(BX=handle, CX:DX=offset) -> DX:AX = new position.  SEEK_SET.
do_lseek:
    mov ax, 0x4200             ; AH=42h, AL=0 (from start)
    int 0x21
    ret

; do_getftime(BX=handle) -> CX=packed time, DX=packed date (INT 21h AH=57h AL=0).
do_getftime:
    mov ax, 0x5700
    int 0x21
    ret

; do_setftime(BX=handle, CX=packed time, DX=packed date) (INT 21h AH=57h AL=1).
do_setftime:
    mov ax, 0x5701
    int 0x21
    ret

; do_delete(DX=path) -> AX=0/-1 (INT 21h AH=41h).
do_delete:
    mov ah, 0x41
    int 0x21
    jc .err
    xor ax, ax
    ret
.err:
    mov ax, -1
    ret

; do_rmdir(DX=path) -> AX=0/-1 (INT 21h AH=3Ah).
do_rmdir:
    mov ah, 0x3A
    int 0x21
    jc .err
    xor ax, ax
    ret
.err:
    mov ax, -1
    ret

; do_rename(DX=old, DI=new) -> AX=0/-1 (INT 21h AH=56h; ES:DI=new).
do_rename:
    push es
    push ds
    pop es                     ; ES = DS (new name in our segment)
    mov ah, 0x56
    int 0x21
    pop es
    jc .err
    xor ax, ax
    ret
.err:
    mov ax, -1
    ret

; putstr(SI=asciiz) — write string to the DOS console, no CRLF.
putstr:
    push ax
    push dx
    push si
.pstr_loop:
    mov dl, [si]
    test dl, dl
    jz .pstr_done
    mov ah, 0x02
    int 0x21
    inc si
    jmp .pstr_loop
.pstr_done:
    pop si
    pop dx
    pop ax
    ret

; puts(SI=asciiz) — write the string + CRLF to the DOS console (cosmetic log).
puts:
    push ax
    push dx
    push si
.loop:
    mov dl, [si]
    test dl, dl
    jz .nl
    mov ah, 0x02
    int 0x21
    inc si
    jmp .loop
.nl:
    mov dl, 13
    mov ah, 0x02
    int 0x21
    mov dl, 10
    mov ah, 0x02
    int 0x21
    pop si
    pop dx
    pop ax
    ret

; ---------------------------------------------------------------------------
; Console messages and lookup tables (part of the image — emit bytes).
; ---------------------------------------------------------------------------
; Banner fragments (start: concatenates these at runtime).
msg_rdyA  db "xfer ready on COM", 0
msg_rdyB  db " at ", 0
msg_rdyC  db " baud - press Q to quit", 0
; Default baud string used when no argument is given.
msg_9600  db "9600", 0
; Usage / error message.
msg_usage db "usage: XFER [baud [com]]  baud 2..115200, com 1..4", 0
; COM port base-address table (indexed by (com-1)*2).
com_tbl   dw 0x3F8, 0x2F8, 0x3E8, 0x2E8

; ---------------------------------------------------------------------------
; Uninitialised data / buffers.  Declared as `equ` offsets just past the code so
; NASM emits NO bytes for them (a COM owns the whole 64 KB segment, so the RAM
; after the image is ours).  This is what keeps XFER.COM tiny — no trailing zeros.
; ---------------------------------------------------------------------------
absbss    equ $
v_fd      equ absbss            ; word
v_wcrc    equ v_fd + 2          ; dword
v_n       equ v_wcrc + 4        ; word
v_got16   equ v_n + 2           ; word
v_type    equ v_got16 + 2       ; byte
v_seq     equ v_type + 1        ; byte
v_dlen    equ v_seq + 1         ; word
v_status  equ v_dlen + 2        ; byte
v_name    equ v_status + 1      ; word
v_rfd     equ v_name + 2        ; word
v_rcrc    equ v_rfd + 2         ; dword
v_dseq    equ v_rcrc + 4        ; byte
v_got     equ v_dseq + 1        ; word
v_ftime   equ v_got + 2         ; dword: packed time(w) + packed date(w) for get/set

rxf       equ v_ftime + 4       ; 600
pk        equ rxf + 600         ; 600
tx        equ pk + 600          ; 600
op        equ tx + 600          ; 600
fbuf      equ op + 600          ; CHUNK (128)
eb        equ fbuf + CHUNK      ; 32
dta       equ eb + 32           ; 128

; parse_args runtime state (populated before uart_init; no emitted bytes).
v_base      equ dta + 128       ; word  — runtime UART base port address
v_div       equ v_base + 2      ; word  — UART baud divisor (115200 / baud)
v_com       equ v_div + 2       ; byte  — COM port number 1..4 (for banner)
v_baud32    equ v_com + 1       ; dword — scratch: 32-bit baud accumulator
v_baudstr   equ v_baud32 + 4   ; word  — near ptr to asciiz baud string
v_baudstr_buf equ v_baudstr + 2 ; 8 bytes — buffer for user-supplied baud digits
