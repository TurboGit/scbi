from pathlib import Path
import pytest

from src.scbi.models import ModuleRef, RefKind, Plan, PlanEntry, PlanSyntaxError
from src.scbi.plan_reader import PlanReader, PlanNotFoundError

SCRIPTS_D = Path(__file__).resolve().parent.parent / "scripts.d"
TEST_SCRIPTS_D = Path(__file__).resolve().parent / "scripts.d"


def reader(discs: set[str] | None = None):
    return PlanReader(SCRIPTS_D, discriminants=discs or set())


def test_reader(discs: set[str] | None = None):
    return PlanReader(TEST_SCRIPTS_D, discriminants=discs or set())


# -----------------------------------------------------------------------
# ModuleRef.parse
# -----------------------------------------------------------------------

def test_parse_simple():
    r = ModuleRef.parse("modA")
    assert r.module == "modA"
    assert r.variant == "default"
    assert r.kind == RefKind.NONE
    assert r.version == "NONE"


def test_parse_with_variant():
    r = ModuleRef.parse("modA/v1")
    assert r.module == "modA"
    assert r.variant == "v1"
    assert r.kind == RefKind.NONE


def test_parse_dotted_variant():
    r = ModuleRef.parse("modA/variant1.variant2")
    assert r.module == "modA"
    assert r.variant == "variant1.variant2"
    assert r.kind == RefKind.NONE


def test_parse_version():
    r = ModuleRef.parse("modA:v1.0")
    assert r.module == "modA"
    assert r.variant == "default"
    assert r.kind == RefKind.BRANCH
    assert r.version == "v1.0"


def test_parse_hash_version():
    r = ModuleRef.parse("modA:#1.0")
    assert r.module == "modA"
    assert r.kind == RefKind.VERSION
    assert r.version == "1.0"


def test_parse_dev():
    r = ModuleRef.parse("modA:dev")
    assert r.module == "modA"
    assert r.kind == RefKind.DEV
    assert r.version == "dev"


def test_parse_variant_version():
    r = ModuleRef.parse("modA/v1:#2.0")
    assert r.module == "modA"
    assert r.variant == "v1"
    assert r.kind == RefKind.VERSION
    assert r.version == "2.0"


def test_parse_variant_dotted_version():
    r = ModuleRef.parse("modA/variant1.variant2:#1.2.3")
    assert r.module == "modA"
    assert r.variant == "variant1.variant2"
    assert r.kind == RefKind.VERSION
    assert r.version == "1.2.3"


def test_parse_skip():
    r = ModuleRef.parse("modA:skip")
    assert r.module == "modA"
    assert r.kind == RefKind.BRANCH
    assert r.version == "skip"


def test_to_string():
    assert str(ModuleRef.parse("modA")) == "modA"
    assert str(ModuleRef.parse("modA/v1")) == "modA/v1"
    assert str(ModuleRef.parse("modA:v1.0")) == "modA:v1.0"
    assert str(ModuleRef.parse("modA:#1.0")) == "modA:#1.0"
    assert str(ModuleRef.parse("modA:dev")) == "modA:dev"
    assert str(ModuleRef.parse("modA/v1:#2.0")) == "modA/v1:#2.0"


# -----------------------------------------------------------------------
# Plan loading — simple plans
# -----------------------------------------------------------------------

def test_load_dev_plan():
    p = reader().load("default")
    assert "c-darktable" in p.modules
    assert "c-gmp" in p.modules


def test_load_simple_entries():
    p = test_reader().load("dev")
    assert p.modules["lib1"].ref_str == "lib1:v1"
    assert p.modules["lib2"].ref_str == "lib2/variant1:dev"


def test_load_meta_plan():
    p = test_reader().load("meta")
    assert p.modules["meta"].ref_str == "meta/cc:v2"


def test_load_inherit_plan():
    p = test_reader().load("inherit")
    assert "lib1" in p.modules


# -----------------------------------------------------------------------
# @set directive
# -----------------------------------------------------------------------

def test_set_directive():
    p = test_reader().load("set")
    assert p.modules["module1"].ref_str == "module1:12"
    assert p.modules["module2"].ref_str == "module2:${UNKNOWN}"
    assert p.modules["module3"].ref_str == "module3/kl:12"
    # Group close overrides version (:${VERSION} → :12)
    assert p.modules["module4"].ref_str == "module4:12"
    assert p.modules["module5"].ref_str == "module5:12"
    assert p.modules["module6"].ref_str == "module6:12"


# -----------------------------------------------------------------------
# @alias directive
# -----------------------------------------------------------------------

def test_alias_directive():
    p = test_reader().load("alias")
    assert p.aliases["p-gnat"] == "c-sandbox"

    p2 = reader().load("default")
    assert p2.aliases["p-gnat"] == "c-sandbox"
    assert p2.aliases["p-gnatmem"] == "c-sandbox"


# -----------------------------------------------------------------------
# @on directive
# -----------------------------------------------------------------------

def test_on_directive_pass():
    # With deb + 12 → matches @on deb,12 (AND) and @on deb
    p = test_reader({"deb", "12"}).load("ondeps")
    assert p.modules["notfound"].ref_str == "notfound"
    assert p.modules["large"].ref_str == "large"
    assert "forv9" not in p.modules           # needs deb,9 — 9 missing
    assert "onlyfor10one" not in p.modules     # needs deb,10.1
    assert "liblua5.2-dev" not in p.modules    # needs deb,10.1
    assert "os@-mylualib" not in p.modules     # needs deb,10.1
    assert p.modules["me"].ref_str == "me:v2"
    assert p.modules["thisisit"].ref_str == "thisisit:#12"


def test_on_directive_fail():
    # deb + 9 → matches @on deb,9 but not @on deb,12 or @on deb,10.1
    p = test_reader({"deb", "9"}).load("ondeps")
    assert p.modules["notfound"].ref_str == "notfound"   # @on deb → matches
    assert "large" not in p.modules                       # needs deb,12
    assert p.modules["forv9"].ref_str == "forv9"          # @on deb,9 → matches
    assert "onlyfor10one" not in p.modules                # needs deb,10.1
    assert p.modules["me"].ref_str == "me:v2"             # unconditional
    assert p.modules["thisisit"].ref_str == "thisisit:#12" # @on deb → matches


# -----------------------------------------------------------------------
# @for directive
# -----------------------------------------------------------------------

def test_for_directive():
    p = test_reader({"deb", "12"}).load("for")
    # @for main use module7:87 → key is "main=module7"
    assert p.modules["main=module7"].ref_str == "module7:87"


# -----------------------------------------------------------------------
# Groups
# -----------------------------------------------------------------------

def test_group_unconditional():
    p = test_reader().load("group")
    assert p.modules["modA"].ref_str == "modA"
    assert p.modules["modB"].ref_str == "modB"
    assert p.modules["modC"].ref_str == "modC"
    assert p.modules["modD"].ref_str == "modD:vA"
    assert p.modules["modE"].ref_str == "modE/new:vB"
    assert p.modules["modF"].ref_str == "modF/grp:vZ"
    assert p.modules["modG"].ref_str == "modG/grp:vZ"
    assert p.modules["modH"].ref_str == "modH/grp:vZ"
    assert p.modules["modI"].ref_str == "modI/hybrid"
    assert p.modules["modJ"].ref_str == "modJ/speed"


def test_group2_syntax_error():
    """group2 has module on same line as [ which is invalid."""
    with pytest.raises(PlanSyntaxError, match="unexpected modB"):
        test_reader().load("group2")


def test_group3():
    p = test_reader().load("group3")
    assert p.modules["modB"].ref_str == "modB/new:vZ"
    assert p.modules["modH"].ref_str == "modH/fast:vB"
    # Group variant replaces member variant (not additive)
    assert p.modules["modC"].ref_str == "modC/fast:vc"
    assert p.modules["modD"].ref_str == "modD/fast:vA"
    assert p.modules["modE"].ref_str == "modE/one:vV"


def test_group4_with_mpi():
    discs = {"mpi"}
    p = test_reader(discs).load("group4")
    assert p.modules["modA"].ref_str == "modA/mpi.fast:master"
    assert p.modules["modG"].ref_str == "modG/mpi:master"
    assert p.modules["modH"].ref_str == "modH/mpi:master"


def test_group4_without_mpi():
    discs = set()
    p = test_reader(discs).load("group4")
    # [ /= mpi → barrier fails → group included with version:master
    assert p.modules["modA"].ref_str == "modA:master"
    assert p.modules["modG"].ref_str == "modG:master"
    assert p.modules["modH"].ref_str == "modH:master"


def test_group4_with_fast():
    discs = {"fast"}
    p = test_reader(discs).load("group4")
    assert p.modules["modH"].ref_str == "modH/fast:rz"


def test_group5_with_deb_1():
    # [ = deb,1 9.3 → group 1 active (deb AND 1)
    # group 2 inverse → skip (deb,9 → deb✓ 1✓ → pass → inverse closes)
    # group 3 [ = deb,1 mpi → active → overwrites modH
    discs = {"deb", "1"}
    p = test_reader(discs).load("group5")
    assert p.modules["modA"].ref_str == "modA/mpi.fast:master"
    assert p.modules["modG"].ref_str == "modG/mpi:master"
    assert p.modules["modH"].ref_str == "modH/fast:rz"


def test_group5_no_discs():
    # No discriminants → [ /= groups activate (inverse barrier passes)
    # [ = groups fail (no matching discriminants)
    discs = set()
    p = test_reader(discs).load("group5")
    assert p.modules["modA"].ref_str == "modA:master"
    assert p.modules["modG"].ref_str == "modG:master"
    assert p.modules["modH"].ref_str == "modH:master"


# -----------------------------------------------------------------------
# Groups in plan files — autobar
# -----------------------------------------------------------------------

def test_autobar_with_deb():
    discs = {"deb"}
    p = test_reader(discs).load("autobar")
    # [ = deb → active → modA/deb
    assert p.modules["modA"].ref_str == "modA/deb"
    # [ = deb → active → modB/deb; [ = deb,9 and [ = deb,10 fail
    assert p.modules["modB"].ref_str == "modB/deb"
    # [ = deb,9.3 → "9.3" not in discs → fail → modC stays top-level
    assert p.modules["modC"].ref_str == "modC"
    # [ = win → fail
    assert p.modules["modD"].ref_str == "modD"
    # [ = 9 → fail
    assert p.modules["modE"].ref_str == "modE"
    # [/= deb → barrier passes → closed → skip → modF stays top-level
    assert p.modules["modF"].ref_str == "modF"
    # [/= deb,9 → barrier fails (9 missing) → included → modG/notdeb9
    assert p.modules["modG"].ref_str == "modG/notdeb9"


def test_autobar_with_deb_9():
    discs = {"deb", "9"}
    p = test_reader(discs).load("autobar")
    # [ = deb → active → modA/deb (no deb-only group for A)

    # modB: [ = deb → modB/deb, overwritten by [ = deb,9 → modB/deb9
    assert p.modules["modB"].ref_str == "modB/deb9"
    # [ = deb,9.3 → "9.3" not a key → fail
    assert p.modules["modC"].ref_str == "modC"
    # [ = win → fail
    assert p.modules["modD"].ref_str == "modD"
    # [ = 9 → active → modE/just9
    assert p.modules["modE"].ref_str == "modE/just9"
    # [/= deb → barrier passes → closed → modF stays top-level
    assert p.modules["modF"].ref_str == "modF"
    # [/= deb,9 → barrier passes (deb AND 9 both match) → closed → modG stays top
    assert p.modules["modG"].ref_str == "modG"


def test_autobar_with_win():
    discs = {"win"}
    p = test_reader(discs).load("autobar")
    # [ = win → active → modD/win (overwrites top-level modD)
    assert p.modules["modD"].ref_str == "modD/win"


def test_autobar_no_disc():
    discs = set()
    p = test_reader(discs).load("autobar")
    # [/= deb → barrier fails (deb missing) → included → modF/notdeb
    assert p.modules["modF"].ref_str == "modF/notdeb"
    # [ = deb → fail → modA stays top-level
    assert p.modules["modA"].ref_str == "modA"
    # [ = win → fail
    assert "modD" not in p.modules or p.modules["modD"].ref_str == "modD"


# -----------------------------------------------------------------------
# @ref directive
# -----------------------------------------------------------------------

def test_ref_as():
    p = test_reader().load("as")
    # @ref lib1:v2 as libVR → lib1 gets libVR's variant/version (BRANCH, no #)
    assert p.modules["lib1"].ref_str == "lib1/variant-no-patch:v1"
    assert p.modules["libVR"].ref_str == "libVR/variant-no-patch:v1"
    assert p.modules["libV"].ref_str == "libV/variant-no-patch"
    assert p.modules["libR"].ref_str == "libR:v1"


# -----------------------------------------------------------------------
# @load recursive
# -----------------------------------------------------------------------

def test_load_recursive():
    p = test_reader().load("final1")
    # r1 loads root (plg1:va, plg2:vb), then plg1:vz overwrites
    # r2 loads root (already loaded), then plg2:vz overwrites
    assert p.modules["plg1"].ref_str == "plg1:vz"
    assert p.modules["plg2"].ref_str == "plg2:vz"


def test_load_recursive_two_levels():
    p = test_reader().load("final2")
    # same result as final1, just different @load order
    assert p.modules["plg1"].ref_str == "plg1:vz"
    assert p.modules["plg2"].ref_str == "plg2:vz"


# -----------------------------------------------------------------------
# Plan not found
# -----------------------------------------------------------------------

def test_plan_not_found():
    with pytest.raises(PlanNotFoundError):
        reader().load("nonexistent")


# -----------------------------------------------------------------------
# File-based test: load all actual test plans and verify they parse
# -----------------------------------------------------------------------

def test_all_test_plans_parse():
    """Verify every .plan-* file in the test scripts.d can be parsed."""
    plan_files = list(TEST_SCRIPTS_D.glob(".plan-*"))
    assert len(plan_files) > 40
    for pf in plan_files:
        name = pf.name.replace(".plan-", "")
        # These need discriminants to parse fully
        skip_without_discs = {"autobar", "group4", "group5", "ondeps", "as"}
    known_bad_plans = {"group2"}  # syntactically invalid per design
    for pf in plan_files:
        name = pf.name.replace(".plan-", "")
        if name in known_bad_plans:
            continue
        try:
            test_reader().load(name)
        except Exception as e:
            pytest.fail(f"Failed to parse {name}: {e}")


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------

def test_empty_lines_and_comments():
    """Blank lines and comments should be ignored."""
    p = test_reader().load("group3")
    assert p.modules["modA"].ref_str == "modA"


def test_plan_with_only_comments():
    """A plan with only comments should produce an empty result."""
    p = test_reader().load("empty")
    assert len(p.modules) == 0


def test_circular_load():
    """@load should not cause infinite recursion."""
    p = test_reader().load("circ-a")
    assert "modA" in p.modules
