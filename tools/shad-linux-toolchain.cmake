# Clang 19 libc++ exposes its C++20 cancellation support with this driver option.
# Apply it to the emulator executable; dependency libraries keep their flags.
function(orbis_linux_cxx_features)
    target_compile_options(shadps4 PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-fexperimental-library>")
    target_link_options(shadps4 PRIVATE -fexperimental-library)
    # Guest unwind sections use GNU __register_frame's section-pointer ABI.
    # Keep libgcc_s before LLVM libunwind in symbol lookup order; LLVM expects
    # individual FDEs and otherwise breaks forced unwinding in pthread_exit.
    target_link_options(shadps4 PRIVATE "LINKER:--no-as-needed" -lgcc_s "LINKER:--as-needed")
    set(orbis_source_vfs "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../build/shad-source-vfs.json")
    if(ORBIS_USE_SOURCE_CACHE AND EXISTS "${orbis_source_vfs}")
        target_compile_options(shadps4 PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-ivfsoverlay${orbis_source_vfs}>")
    endif()
endfunction()
cmake_language(DEFER CALL orbis_linux_cxx_features)
