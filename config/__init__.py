"""Project package.

PyMySQL is used as a pure-Python MySQL driver so the project installs on
Windows without a C compiler. It is registered as the ``MySQLdb`` module that
Django's MySQL backend expects.
"""
try:
    import pymysql

    pymysql.version_info = (2, 2, 1, "final", 0)  # satisfy Django's driver version check
    pymysql.install_as_MySQLdb()
except ImportError:  # SQLite-only environments
    pass
