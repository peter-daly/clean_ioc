from pathlib import Path

from setuptools import setup


def read(*filenames, **kwargs):
    encoding = kwargs.get("encoding", "utf-8")
    sep = kwargs.get("sep", "\n")
    buf = []

    for filename in filenames:
        with open(filename, encoding=encoding) as f:
            buf.append(f.read())

    return sep.join(buf)


this_directory = Path(__file__).parent
long_description = (this_directory / "README.rst").read_text()

setup(
    name="clean_ioc",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    url="https://github.com/peter-daly/clean_ioc",
    license="MIT",
    author="Peter Daly",
    author_email="petecdaly@gmail.com",
    description="A simple and unintrusive dependency injection for Python 3.10 +",
    long_description=long_description,
    packages=["clean_ioc"],
    package_data={"clean_ioc": ["CHANGES.md"]},
    include_package_data=True,
    platforms="any",
    classifiers=[
        "Programming Language :: Python",
        "Development Status :: 4 - Beta",
        "Natural Language :: English",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
    ],
)
