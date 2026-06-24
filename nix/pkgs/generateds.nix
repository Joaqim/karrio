{
  buildPythonPackage,
  fetchPypi,
  six,
  lxml,
  requests,
}:
buildPythonPackage rec {
  pname = "generateDS";
  version = "2.44.3";
  format = "wheel";

  # The current release publishes only a wheel.
  src = fetchPypi {
    inherit pname version format;
    dist = "py3";
    python = "py3";
    hash = "sha256-rl23EFyndxgrplSRGMmroWkOo0FACvE/+9v74bwCIpk=";
  };

  dependencies = [
    six
    lxml
    requests
  ];

  pythonImportsCheck = [ "libgenerateDS" ];

  # The published `generateDS` console entry point imports a non-existent
  # top-level module and crashes; the working program ships as the
  # `generateDS.py` script. karrio's schema generators invoke the documented
  # `generateDS` command, so point it at the functional script.
  postFixup = ''
    ln -sf generateDS.py $out/bin/generateDS
  '';

  meta = {
    description = "Generate Python data structures and an XML parser from an XML Schema";
    homepage = "https://www.davekuhlman.org/generateDS.html";
  };
}
