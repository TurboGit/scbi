"""Functions of the Bash runtime (scripts.d/[0-9]*, _os_*): a command
hook calling one which is not a built-in of the command language does
not convert (checked against the runtime files by test_liftcmd.py)."""

RUNTIME_FUNCTIONS = frozenset("""
add-to-list add-to-var add-to-var-sep all-variants all-variants-v
append-to-list append-to-var append-to-var-sep built-compiler
call-variant-hooks check-archive-exists check-auto-variant check-barrier
check-cos-pkg check-deb-pkg check-dependency-tree check-fed-pkg
check-mingw-pkg check-module-version check-none-pkg check-pkg
check-pkg-status check-rhl-pkg check-ubt-pkg check-versions
check-win-pkg clean-scbi-logs clean-version-string clog
c-log-message comment-out-block compute-log-stat-file copy-function
copy-module-src-callback create-standalone-package define-var
display-build-plan display-file display-log-stat display-modules
display-plans display-stacktrace display-stat display-time display-timing
dlog elog fn-exists for-all-direct-modules-with-meta-ext for-all-modules
for-all-modules-build-depends-with-meta for-all-modules-depends-with-meta
for-all-modules-ext for-all-modules-tests-depends-with-meta
for-all-modules-with-meta for-all-modules-with-meta-ext for-final-modules
get-all-depends get-archive get-archive-data get-branch get-build-dir
get-build-id get-build-id-callback get-build-type get-caller
get-config-options get-content-md5 get-cos-install-md5 get-deb-install-md5
get-deb-lib-for-dev get-depends-build-id get-distrib get-fed-install-md5
get-generic-build-id-callback get-hook get-hook-value get-install-log
get-install-md5 get-lib-for-dev get-ln get-md5 get-meta-build-id-callback
get-min-avr-max get-mingw-install-md5 get-module-display-ref get-module-name
get-module-ref get-module-version get-os-bin get-os-bin-dir get-os-file
get-os-inc get-os-inc-dir get-os-lib get-os-lib-dir get-patch-md5 get-pkg-name
get-pkg-version get-rhl-install-md5 get-source-dir get-string-md5 get-timer
get-ubt-install-md5 get-var-md5 get-vcs get-vcs-commit-id get-vcs-data
get-vcs-dir get-vcs-display-ref get-vcs-ref get-vcs-user-co-dir
get-version get-version-number get-win-install-md5 git-branch git-co
git-set-submodule-url gprbuild-project handle-plan-auto-variant
handle-plan-meta-module has-discriminant has-variant hg-branch hg-co ilog
inherit-plugin _inherit-plugin_internal init-alias init-cos-pkg init-deb-pkg
init-distrib-alias init-fed-pkg init-mingw-pkg init-none-pkg init-rhl-pkg
init-ubt-pkg init-win-pkg _internal_copy-plugin _internal_for-all-modules
_internal_for-final-modules _internal_get-branch _internal_get-hook
_internal_list-build-plan _internal_merge_variant is-enabled is-hook-true
is-in-list is-in-var-sep is-meta-aggregate-module is-meta-module
last-modified-directory line-sep load-module load-module-plan
load-runtime-module-plan module-apply-patch module-clean-install
module-install module-patch module-plan-md5 module-pre-install
module-purge module-purge-tvdir module-setup no-target-env output-string-md5
parallel-do parse-module-ref plugin-call-env-hooks plugin-call-variant-hooks
plugin-get-variant-hooks pop-dependency-tree prepend-to-list prepend-to-var
prepend-to-var-sep push-dependency-tree record-build-plan register-module-plan
remove-from-list remove-from-var remove-from-var-sep rewrite-module-plan
scbi-store scbi-store-get-key scbi-store-list-keys scbi-store-set-key
send-mail set-compiler-paths set-module-ref set-proxy set-timer
setup-discriminants set-var show-command store-cached-plan svn-branch
svn-co sync-dir system-compiler target-env unset-var vcs-build-id with-variant
""".split())
