
from scbi.discriminants import (
    HostInfo,
    LsbInfo,
    forced_discriminants,
    get_distrib,
    setup_discriminants,
)


def lsb(desc, release, distributor, codename):
    return LsbInfo(
        description=f"Description:\t{desc}",
        release=f"Release:\t{release}",
        distributor=f"Distributor ID:\t{distributor}",
        codename=f"Codename:\t{codename}",
    )


HOSTS = {
    "debian12": lsb("Debian GNU/Linux 12 (bookworm)", "12", "Debian", "bookworm"),
    "debian-sid": lsb("Debian GNU/Linux forky/sid", "n/a", "Debian", "sid"),
    "ubuntu": lsb("Ubuntu 22.04.3 LTS", "22.04", "Ubuntu", "jammy"),
    "fedora": lsb("Fedora release 39 (Thirty Nine)", "39", "Fedora", "ThirtyNine"),
    "centos": lsb("CentOS Linux release 7.9.2009 (Core)", "7.9.2009", "CentOS", "Core"),
    "redhat": lsb("Red Hat Enterprise Linux 9.2 (Plow)", "9.2", "RedHatEnterprise", "Plow"),
    "other": lsb("Arch Linux", "rolling", "Arch", "n/a"),
}


def host(name, domain="example.org"):
    return HostInfo(HOSTS[name], "x86_64", "mybox", domain)


def test_get_distrib():
    assert get_distrib(host("debian12")) == "deb"
    assert get_distrib(host("ubuntu")) == "ubt"
    assert get_distrib(host("other")) == "none"
    assert get_distrib(HostInfo(LsbInfo(), "", "", "", is_windows=True)) == "win"
    assert get_distrib(HostInfo(LsbInfo(), "", "", "", True, "/mingw64")) == "mingw"


def test_debian():
    info = setup_discriminants(host("debian12"), "x86_64-linux-gnu", "x86_64-linux-gnu")
    assert info.name == "deb"
    assert info.version == "12" and info.major_version == "12"
    assert info.as_set() == {
        "deb", "debian", "gnu", "linux", "12", "bookworm", "x86_64",
        "mybox", "example.org", "native",
    }


def test_cross():
    info = setup_discriminants(host("debian12", ""), "x86_64-linux-gnu", "arm-linux-gnueabi")
    assert {"cross", "target-arm", "target-linux", "target-gnueabi"} <= info.as_set()
    assert "" not in info.as_set() and "native" not in info.as_set()


def test_forced():
    assert forced_discriminants("deb", "10.1", "10") == ["10", "10.1", "deb"]
    assert forced_discriminants("", "", "") == ["default"] * 3


FAKE_TOOLS = r"""
mkdir -p fakebin
cat > fakebin/lsb_release <<EOF
#!/bin/bash
case "\$1" in
  -d) printf 'Description:\t%s\n' "$1" ;;
  -r) printf 'Release:\t%s\n' "$2" ;;
  -i) printf 'Distributor ID:\t%s\n' "$3" ;;
  -c) printf 'Codename:\t%s\n' "$4" ;;
esac
EOF
cat > fakebin/hostname <<EOF
#!/bin/bash
[[ "\$1" == --short ]] && echo mybox
[[ "\$1" == --domain ]] && echo "$5"
true
EOF
cat > fakebin/uname <<EOF
#!/bin/bash
echo x86_64
EOF
chmod +x fakebin/*
PATH=$PWD/fakebin:$PATH
SCBI_TARGET=$6
SCBI_OS_NAME=$(get-distrib)
SCBI_OS_DISCRIMINANTS=([$SCBI_OS_NAME]="yes")
setup-discriminants
printf '%s\n' "$SCBI_OS_NAME" "$SCBI_OS_VERSION" "$SCBI_OS_CODENAME" "$SCBI_OS_MAJOR_VERSION" "$SCBI_OS_ID"
echo "${!SCBI_OS_DISCRIMINANTS[@]}"
"""
