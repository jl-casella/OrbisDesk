"""Check the LLVM source closure needed by the clean libc++ configure."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('build_product', Path(__file__).with_name('build-product.py'))
product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(product)


class ProductSourceTests(unittest.TestCase):
    def test_llvm_lit_cmake_dependency_is_included(self):
        for name in ('llvm/utils/llvm-lit/CMakeLists.txt', 'llvm/utils/llvm-lit/llvm-lit.in',
                     'llvm/utils/lit/lit/main.py', 'llvm/cmake/modules/AddLLVM.cmake',
                     'runtimes/CMakeLists.txt', 'libcxx/CMakeLists.txt'):
            with self.subTest(name=name):
                self.assertTrue(product.llvm_runtime_member('llvm-project-21.1.6.src/' + name))

    def test_unrelated_llvm_sources_are_excluded(self):
        for name in ('llvm/lib/CodeGen/CodeGen.cpp', 'llvm/utils/lit-unrelated/file',
                     'llvm/utils/llvm-lit-unrelated/file', 'llvm/cmake-unrelated/file',
                     'clang/CMakeLists.txt'):
            with self.subTest(name=name):
                self.assertFalse(product.llvm_runtime_member('llvm-project-21.1.6.src/' + name))


if __name__ == '__main__':
    unittest.main()
