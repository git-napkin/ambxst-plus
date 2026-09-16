# Optional TypeSafe Python SDK (Jev). Missing at runtime is a clean non-Jev fallback.
# Pinned from PyPI wheels so the build does not need uv_build / hatch VCS hooks.
#
# Applied as python3.packageOverrides so the interpreter has a single idna.
# httpx2 2.13.0 requires idna>=3.18; nixpkgs currently ships 3.11.
{ pkgs }:

self: super:

let
  inherit (pkgs) fetchurl lib;
  py = self;

  buildWheel = {
    pname,
    version,
    url,
    hash,
    dependencies ? [ ],
    imports ? [ ],
  }:
    py.buildPythonPackage {
      inherit pname version;
      format = "wheel";
      src = fetchurl { inherit url hash; };
      propagatedBuildInputs = dependencies;
      doCheck = false;
      pythonImportsCheck = imports;
    };
in rec {
  idna = buildWheel {
    pname = "idna";
    version = "3.18";
    url = "https://files.pythonhosted.org/packages/1e/5e/d4e9f1a599fb8e573b7b87160658329fbf28d19eac2718f51fc3def3aa5a/idna-3.18-py3-none-any.whl";
    hash = "sha256-f5UsvnILaIBV4/h94U9cPl/aqLw5KJhcQHfKaJ3oSaI=";
    imports = [ "idna" ];
  };

  httpcore2 = buildWheel {
    pname = "httpcore2";
    version = "2.13.0";
    url = "https://files.pythonhosted.org/packages/7e/0d/117a771a2bb91df334b66bf4da14cd02f21aefbcfe53180f336ce55e8f90/httpcore2-2.13.0-py3-none-any.whl";
    hash = "sha256-Na5b40eqQEZ7Sl3AMqxn67bScYn8l+jOvPmWFvahu54=";
    dependencies = [ py.h11 ] ++ lib.optionals (py ? truststore) [ py.truststore ];
    imports = [ "httpcore2" ];
  };

  httpx2 = buildWheel {
    pname = "httpx2";
    version = "2.13.0";
    url = "https://files.pythonhosted.org/packages/fe/d1/a0c72b0e006df654709fbc366cc5bcb53e5aee13e1e3395152c6dd293376/httpx2-2.13.0-py3-none-any.whl";
    hash = "sha256-/BJyDO33L6omzKa0yjlOBciU59eTP8Rcr+dnlggE5Jo=";
    dependencies = [
      httpcore2
      py.anyio
      idna
    ] ++ lib.optionals (py ? truststore) [ py.truststore ]
      ++ lib.optionals (py ? typing-extensions) [ py.typing-extensions ];
    imports = [ "httpx2" ];
  };

  typesafe-sdk = buildWheel {
    pname = "typesafe-sdk";
    version = "0.6.0";
    url = "https://files.pythonhosted.org/packages/2e/0d/e99f9622354aeb7205ee4ffded0ac7b4cc38f0981e463e90940578cc10f6/typesafe_sdk-0.6.0-py3-none-any.whl";
    hash = "sha256-IVWdVVjpWn7gCNCgRKYLtbstOx7EJv4Vin83rzW6MjI=";
    dependencies = [
      httpx2
      py.msgspec
      py.tenacity
    ] ++ lib.optionals (py ? typing-extensions) [ py.typing-extensions ];
    imports = [ "typesafe_sdk" ];
  };
}
