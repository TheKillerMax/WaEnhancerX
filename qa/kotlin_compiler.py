"""Launch the installed Kotlin distribution without Windows batch parsing."""
import os
from pathlib import Path

def compiler_command(compiler, kotlin_home=None):
    compiler = Path(compiler).resolve()
    home = Path(kotlin_home).resolve() if kotlin_home else compiler.parents[1]
    lib = home / 'lib'
    if not compiler.is_file() or not (lib / 'kotlin-stdlib.jar').is_file():
        raise RuntimeError('Incomplete Kotlin distribution: ' + str(home))
    if os.name != 'nt':
        return [str(compiler)]
    for name in ('kotlin-preloader.jar', 'kotlin-compiler.jar'):
        if not (lib / name).is_file():
            raise RuntimeError('Kotlin distribution JAR missing: ' + str(lib / name))
    # Match the distribution's kotlinc.bat launcher, preserving each argument.
    # Adding every lib/*.jar would also load bundled compiler plugins in the
    # parent classloader and can shadow an explicitly selected -Xplugin JAR.
    return ['java', '-Xmx512M', '-Xms128M',
            '--add-opens=java.base/java.util=ALL-UNNAMED',
            '-Dkotlin.home=' + str(home), '-cp', str(lib / 'kotlin-preloader.jar'),
            'org.jetbrains.kotlin.preloading.Preloader',
            '-cp', str(lib / 'kotlin-compiler.jar'),
            'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-kotlin-home', str(home)]
