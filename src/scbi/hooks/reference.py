"""Reference definitions of the runtime functions ported to Python.

SHA-256 of the ``declare -f`` text of each function of scripts.d whose
behaviour is reproduced in Python (env.py, hooks/builtins.py, modref.py,
vercmp.py). When a loaded definition differs (redefined by the user, in
the runtime files, an environment file or a plug-in), the driver runs
the Bash functions instead of the Python ports (scbi.hooks.policy).

Generated from scripts.d; tests/unit/test_hooks_policy.py checks it is
up to date.
"""

REFERENCE = {
    "define-var": "7b9042ecd43a682ff345f52076f95140285e58ee5bc3ff4c3aefe6aa30e60371",
    "add-to-var": "a2430a935669c60453ecc09fdbaac186bbba5242a349e348787efc8cd702b9e7",
    "prepend-to-var": "a9becd66c64da025edbd02941ca31bd0cddf68b354350b9f7635cae9543f19ff",
    "append-to-var": "d62e4ee2b9dfa404de915af6ec6c95f644302857a5a3ea6626a05eae3979bbf6",
    "remove-from-var": "69678c479c396bc8c729dd5d3b4ba398028e252ea4713bd349b380951290ca8a",
    "set-var": "ad588a677b011d448cb0109a8c59d524715ce66ec27f07acc25ddb7951ae98f5",
    "unset-var": "8814ade2d4d3a07070c185edc3f47e9c92c888b5b8fbab4ebc8106b376e5614f",
    "add-to-var-sep": "1415c64b3e228e1729052c9fa5a13e622f3210d219fe710d12812e2708661abb",
    "prepend-to-var-sep": "0a85611c123e5db81dd1e715beb917ae97860b7feb7c9825fe3678bd4a92593c",
    "append-to-var-sep": "103116bfcbf11e1d4473ec3d7ab79cfc7086c0b02f0d6737bbfb94dafad362e6",
    "remove-from-var-sep": "0bad8711e5db099d45c58bbde10b3136fa5599ed6f21d523609a4261fbef830d",
    "add-to-list": "3aa56687e49a419a53744052f61bd3a16145ab324f0dd9708d0e44e6147bc102",
    "prepend-to-list": "5cd4c59b9969618a32071231fa31e9a77332e4275290db75ba5a45cc3af8ff6b",
    "append-to-list": "3665eb3b0149dce55e1946e2d691eb5f29fa9717b435e69ea18c561f489c1b56",
    "remove-from-list": "450f0ef61d204cd8afea8c1363e16bcd846d4f0c10a24dc868a66dd221e13db5",
    "is-in-list": "eecd0ab8f172a94d9e3d1e78414fd5a8fe21164eeb51548c14ee8ecd33309c75",
    "system-compiler": "c571d251f4f1e32456b5c6cd118f6d356c23e43f7532b44c3e085fdb2f84c590",
    "set-compiler-paths": "e183a9baf6000c0c0e2aa34b5892c35470d942ffa00891e0d25711453c783796",
    "target-env": "e380dba71553b3d8ff8206c0d10392c7b14e95bfff38e81af1ca3a2c6293307c",
    "no-target-env": "a05b2fd07e05bd8312fc96a440898dd115189bfa14f0417b2e622acc9f6046d7",
    "last-modified-directory": "82fa1768e6f22ab0c99aafc9870f36e0d783220b64e8111874aadcc51b83ec2a",
    "get-os-file": "21d6ce431ff81b713cafec20d5b45d3e8c34ca0f713127238aa9038cf83d9741",
    "get-os-inc": "1e493f34d6e30253361c918b0fe0a53ecc368a44f8567f16e9ad50fa5cf13ec1",
    "get-os-inc-dir": "6bb6d8d2d28e61fe1ebcace3b62d1c4370986fffa7c457ea0ffb4f11e7947615",
    "get-build-type": "6dbd72aa104f7897d4fe4c51d258bb1d0b674cc43ffd297643f22adf73685fc4",
    "is-enabled": "0173fc2c610c3cdabda0e70bdca8d963c283958aa8b725ad5d24f606004f9d6c",
    "get-version": "9ea20205727339662aa6a6d0035923260cc382566312b725d745da73ec7573ac",
    "get-module-version": "d8828caa56c4ea72258b686a13bafb0c39645d9e63edb87df49d5fd90fff99b2",
    "get-module-ref": "ec4e528176072d7710a1aea512cd61661f57fe0068718c7532958051e325fec6",
    "parse-module-ref": "a67d856f4115d8d3f8aaa2db30ef53c598e767e75c84074603d85d627ac2c829",
    "get-caller": "a07ae2a29aad61c75c5d61ddcf29e7d7afa75e00714d11b35711ac3d27702e7b",
    "check-versions": "3d403c1f0456036dd21e7300fa8e1fa86524a5677bf6a4e0e2d14f064defaa14",
    "all-variants-v": "cd9e777cccef70558753dc4e11707c06a75a9ab50f7bd4f50914919b459ac28e",
    "has-variant": "9a4b03cc4fb4677ef3f60c368b195f6828d5aa3a4819a9a66ee37d0ad2228f93",
}
