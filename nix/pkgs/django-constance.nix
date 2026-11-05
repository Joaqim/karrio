{
  lib,
  buildPythonPackage,
  fetchPypi,
  setuptools,
  setuptools-scm,
  django,
}:
buildPythonPackage rec {
  pname = "django-constance";
  version = "4.3.5";
  pyproject = true;

  src = fetchPypi {
    # The published sdist normalizes the name with an underscore
    # (django_constance-4.3.5.tar.gz), which fetchPypi will not derive from a
    # hyphenated pname.
    pname = "django_constance";
    inherit version;
    hash = "sha256-CBF3SD0nK2ZM92jernb8L7sKd3B29FYgtv3k2Qde4rM=";
  };

  # Version is declared dynamic and resolved by setuptools_scm. Building from
  # the sdist there is no git metadata, so pin the version explicitly.
  env.SETUPTOOLS_SCM_PRETEND_VERSION = version;

  build-system = [
    setuptools
    setuptools-scm
  ];

  dependencies = [
    django
  ];

  # Upstream tests require a configured Django project.
  doCheck = false;

  pythonImportsCheck = [ "constance" ];

  meta = {
    description = "Django live settings with pluggable backends, including Redis";
    homepage = "https://github.com/jazzband/django-constance";
    license = lib.licenses.bsd3;
  };
}
