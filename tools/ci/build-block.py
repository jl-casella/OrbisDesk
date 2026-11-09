#!/usr/bin/env python3
"""Build and seal one dependency block from a clean workspace (prebuilt-blocks workflow).

The same functions as build-product.py, then the same seal; publication is prebuilt.py publish.
"""
import argparse
from product_blocks import (build_graphics, build_wine, graphics_environment, prepare_sources,
                            require_clean_workspace, wine_prerequisites)
from product_cache import BLOCKS, ProductCache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--block', choices=BLOCKS, required=True)
    args = parser.parse_args()
    require_clean_workspace()
    cache = ProductCache('cold')
    cache.use(args.block)   # records the cold status; never restores
    prepare_sources()
    if args.block == 'graphics':
        build_graphics(graphics_environment())
    else:
        wine_prerequisites()
        build_wine()
    cache.save(args.block)


if __name__ == '__main__':
    main()
