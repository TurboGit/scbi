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

#  Other ported runtime functions: each one falls back to the Bash function
#  on its own when redefined (scbi.hooks.policy.is_reference), without
#  changing how the environment actions are evaluated.
PORTED = {
    "get-vcs-data": "9d043762cf09dc51ea9ae4fbf008652cca51d3a0263e3f3ef452f1bb8016b9b2",
    "get-archive-data": "43f16efcdbb62212bce366478618c6fe7ea2de8c4c6f62910a6ddeae76e8941f",
    "check-archive-exists": "04a05aad108efc51e49db470bb1b3f058335c4e6ad5072e7238b36128429d41b",
    "get-vcs-dir": "a819b4d16442f1b4b79defd09c6be8b8a0e7e6a604090384c76c261bd14257a3",
    "get-vcs-display-ref": "c75091fcd359bc2bfffe0bb45ce0b0258e09c1db716819ff2686a93cb1ae7b88",
    "get-build-id": "18a17dc3b26bbeab0e0e71b47aa4226d23ba7b44f84a9d5aaf7044021fe0c673",
    "get-depends-build-id": "58e24dd3b19d56058afe14692f9e1c8c04e5cb83915c0ab73539318076d9b5c6",
    "get-patch-md5": "714527cda72e60f88c51d5a7a9b44fe5d111615133a290ee05fd518a200ba622",
    "get-vcs-user-co-dir": "21262128a6ef3725bc8e8fad15cd3b17577d6914621a96407a3afd15a4b7ad60",
    "get-vcs": "327187f3dba1f06e12da163402e2b274e23807e510396a99255472c3438e8bf5",
    "get-branch": "d12fd00aa7c1a72ab1062a92ad205dd0ab0c395b509fca3f73a4625b6f3c8d38",
    "_internal_get-branch": "75cbc67a362d163100933c81ebf3efd91065a60841cd82f1ae9a45e98c3a6b2f",
    "vcs-build-id": "c88b578c2959d2c515ee4755647b809e6ff6d6edfaa3838a03746dbf8f6e1c83",
    "get-vcs-ref": "ad7cf72637d5005d87e942b3a82a000996a9996ba80b6536d36da9670453ece6",
    "get-vcs-commit-id": "3db1050d841fddd86f5697b26b2502d973789fbba2b796c92bfeaea011c6fbd3",
    "get-archive": "80c9ab3067ea68ca279031cf53492ed8aedf63ae837ed1786db05091311953b0",
    "set-proxy": "ca2bb20028652aa4f51c0f7774747674b3f5816e270bb49b318ab12a99409168",
    "get-ln": "655910b838f39726d587385b3bc1625e678cd412bb12b4a4d8b23dcc11e734d2",
    "git-co": "a426f4e6f2300eb78fd3308031f057c1f8a81f25dfdbb3f317a312c7caa65098",
    "git-branch": "b056205563880a52d3181740260b8aacef12cd8038d0d904ccc7fa2ac818ca91",
    "git-set-submodule-url": "54d3bb5f68daac1356a8d84725c818064b834b0acc108848511a098a71394245",
    "hg-co": "84e978e572717f2bb3f63e63bf05664b77e8a166d2bb13cfead39ec32a753578",
    "hg-branch": "2f754afeac7fbb3d099809650cd03289c826c27177dfe73e15c938c6c097cee9",
    "svn-co": "39b4310cbf37bf275b12386d50563fb6b5c2704396dedcad1185fa9fd56e9f5b",
    "svn-branch": "1e296a772ce7bc58b1a5a560168151c46e6fb01e95a1e76108a0400e4bbe48c8",
    "module-setup": "e8c11c4c4706b7dc4f409d97841f33f7d7f5e48a0298d34c523229af626dde87",
    "module-patch": "5ff6ec136480ccd5ecdbfb18860db06f8610e7e10c4b2524a5292891b8d47f44",
    "module-apply-patch": "2a00d523bc8603b3f2adee1de54f28fd878cda93e78238db78e7f3b34a5304d4",
    "module-purge": "ff628083937eb7ab7993f2c02b644d6ed1cbe4de8f5e5b7062228b6ad6c3ac04",
    "module-purge-tvdir": "cec52973e098ad9ba08e480a02f0e16fed1c21e7a5fd9f9749eb0d3ce11d2896",
    "module-pre-install": "08bc66a306dfea311fd8eba216082a65a56bf9e65171c2da97a26d5aab54707c",
    "module-install": "0d8bf8e73be2b869692634767af174186c37f7c754f7fa43fb9c5ce0e1d6540c",
    "module-clean-install": "1c241706b4fd248e16b54123c69eced0baf06c1211f8fc9649347dff1aef0baf",
    "sync-dir": "329818085f39a943e83bedb10df1d899ef2c470a5eea7379814acb98a25a50c3",
    "get-md5": "e13a8355affecbcc12eebd36321ff36c2aecbf13809e684631a889e34c2443ec",
    "show-command": "a77eeddff7ac8015382fc069b59d5a4116fe0dd30d10f2338ab84b766d80772c",
    "_internal_copy-plugin": "29e37c40da62df607213a9e4bd88351a8f142acea460376ee395a98189225b6c",
}
