import os
import sys
import tarfile
if sys.version_info >= (3, 14):
    from compression import zstd
else:
    from backports import zstd


def _zstdopen(name, mode="r", fileobj=None, compresslevel=9, **kwargs):
    """Open zstd compressed tar archive name for reading or writing.
    """
    if mode not in ("r", "w", "x"):
        raise ValueError("mode must be 'r', 'w' or 'x'")

    try:
        level_arg = {} if mode[0] == 'r' else {"level": compresslevel}
        fileobj = zstd.ZstdFile(name, mode + "b", **level_arg)
    except OSError as e:
        if fileobj is not None and mode == 'r':
            raise tarfile.ReadError("not a zstd file") from e
        raise

    try:
        t = tarfile.TarFile.taropen(name, mode, fileobj, **kwargs)
    except OSError as e:
        fileobj.close()
        if mode == 'r':
            raise tarfile.ReadError("not a zstd file") from e
        raise
    except BaseException:
        fileobj.close()
        raise
    t._extfileobj = False
    return t


tarfile.TarFile.OPEN_METH['zstd'] = 'zstdopen'
tarfile.TarFile.zstdopen = _zstdopen


def compress(name: str, files: list[str] | str, level=3):
    """
    name: path name to the output file
    files: path name of files to compress
    level: compression level
    """
    if isinstance(files, str):  # typical
        files = [files]
    name = name.removeprefix('./')

    ext = os.path.splitext(name)[1].removeprefix('.')
    if not ((ext == 'tar') or (ext in tarfile.TarFile.OPEN_METH)):
        raise Exception(f"Unknown compression mode {ext}")

    with tarfile.TarFile.open(name, 'w:' + ext, compresslevel=level) as tf:
        for f in files:
            tf.add(f.removeprefix('./'))


def decompress(name: str, curdir='./'):
    """
    name: path name of the intput file to decompress
    curdir: output directory
    """
    if not tarfile.is_tarfile(name):
        raise Exception(f"'{name}' is not a tar archive.")

    with tarfile.TarFile.open(name, 'r:*') as tf:
        tf.extractall(path=curdir)


if __name__ == '__main__':
    import os
    import pathlib

    dir = './test_zstd_dir'
    os.makedirs(f'{dir}', exist_ok=True)
    pathlib.Path(f'{dir}/test_file').write_text("Hello World!")

    compress(f'{dir}/test_file.tar.zstd', f'{dir}/test_file')

    decompress(f'{dir}/test_file.tar.zstd', './test_file_out')
