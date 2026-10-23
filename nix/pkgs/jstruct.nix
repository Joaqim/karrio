{
  buildPythonPackage,
  fetchPypi,
  attrs,
}:
buildPythonPackage rec {
  pname = "jstruct";
  version = "2021.11";
  format = "wheel";

  # Only a wheel is published to PyPI; there is no source distribution.
  src = fetchPypi {
    inherit pname version format;
    dist = "py3";
    python = "py3";
    hash = "sha256-Cxp/P4jjQFGzcpU+Dm+IxGXd2EzdfhXl3hCo7raGNIU=";
  };

  dependencies = [
    attrs
  ];

  pythonImportsCheck = [ "jstruct" ];

  meta = {
    description = "attrs-based struct helpers used by karrio carrier mappers";
    homepage = "https://github.com/karrioapi/jstruct";
  };
}
