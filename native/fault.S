/* SPDX-License-Identifier: GPL-2.0-or-later */
.text
.globl pw_fault_load, pw_fault_insn, pw_fault_resume
.type pw_fault_load,@function
pw_fault_load:
pw_fault_insn:
    mov (%rdi), %eax
pw_fault_resume:
    ret
.size pw_fault_load, .-pw_fault_load
.globl pw_fault_store, pw_store_insn, pw_store_resume
.type pw_fault_store,@function
pw_fault_store:
    xor %eax, %eax
pw_store_insn:
    mov %esi, (%rdi)
pw_store_resume:
    ret
.size pw_fault_store, .-pw_fault_store
.section .note.GNU-stack,"",@progbits
