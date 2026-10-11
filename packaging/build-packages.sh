#!/usr/bin/env bash
# Construye los paquetes de MelfPaint en dist/.
#
#   packaging/build-packages.sh [deb|rpm|arch|tarball|all]...
#
# - deb:   usa dpkg-deb si existe; si no, arma el .deb con ar y tar.
# - rpm:   necesita rpmbuild (paquete rpm-build en Fedora, rpm-tools en Arch).
# - arch:  necesita makepkg (Arch Linux y derivadas).
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/app/version.py")"
NAME="melfpaint"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
TARBALL="$DIST/$NAME-$VERSION.tar.gz"

if [[ -z "$VERSION" ]]; then
    echo "No se pudo leer la versión de app/version.py" >&2
    exit 1
fi

mostrar_ayuda() {
    sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

paso() { printf '\n==> %s\n' "$*"; }

# El tarball se rehace en cada ejecución: reutilizar uno viejo empaquetaría
# código desactualizado. Con "all" se construye una sola vez.
TARBALL_FRESCO=0

construir_tarball() {
    paso "Código fuente $NAME-$VERSION.tar.gz"
    mkdir -p "$DIST"
    # Se empaqueta el árbol de trabajo (incluye cambios aún sin confirmar).
    tar -C "$ROOT" \
        --exclude='__pycache__' --exclude='*.pyc' \
        --sort=name --owner=0 --group=0 --numeric-owner \
        --mtime="@${SOURCE_DATE_EPOCH:-$(date +%s)}" \
        --transform "s,^,$NAME-$VERSION/," \
        -czf "$TARBALL" \
        app LICENSE README.md Makefile packaging
    TARBALL_FRESCO=1
    echo "$TARBALL"
}

construir_deb() {
    paso "Paquete .deb"
    local staging="$BUILD/deb/${NAME}_${VERSION}-1_all"
    rm -rf "$staging"
    mkdir -p "$staging/DEBIAN"
    make -C "$ROOT" --no-print-directory install DESTDIR="$staging" PREFIX=/usr PYTHON=/usr/bin/python3 >/dev/null

    # Debian guarda la licencia como /usr/share/doc/<paquete>/copyright.
    rm -rf "$staging/usr/share/licenses"
    {
        echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
        echo "Upstream-Name: MelfPaint"
        echo "Source: https://github.com/movacx/MelfPaint"
        echo
        echo "Files: *"
        echo "Copyright: 2026 Herlin Chavarria"
        echo "License: GPL-3+"
        echo " This program is free software: you can redistribute it and/or modify it"
        echo " under the terms of the GNU General Public License as published by the"
        echo " Free Software Foundation, either version 3 of the License, or (at your"
        echo " option) any later version."
        echo " ."
        echo " This program is distributed in the hope that it will be useful, but"
        echo " WITHOUT ANY WARRANTY; without even the implied warranty of"
        echo " MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General"
        echo " Public License for more details."
        echo " ."
        echo " On Debian systems, the complete text of the GNU General Public License"
        echo " version 3 can be found in /usr/share/common-licenses/GPL-3."
    } > "$staging/usr/share/doc/$NAME/copyright"
    gzip -9n "$staging/usr/share/doc/$NAME/README.md"

    local size
    size="$(du -sk --exclude=DEBIAN "$staging" | cut -f1)"
    sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$size/" "$ROOT/packaging/deb/control.in" > "$staging/DEBIAN/control"
    (cd "$staging" && find usr -type f -print0 | sort -z | xargs -0 md5sum) > "$staging/DEBIAN/md5sums"
    find "$staging" -type d -exec chmod 755 {} +
    chmod 644 "$staging/DEBIAN/control" "$staging/DEBIAN/md5sums"

    local salida="$DIST/${NAME}_${VERSION}-1_all.deb"
    mkdir -p "$DIST"
    rm -f "$salida"
    if command -v dpkg-deb >/dev/null 2>&1; then
        dpkg-deb --root-owner-group -Zxz --build "$staging" "$salida" >/dev/null
    else
        # Formato .deb: archivo ar con debian-binary, control.tar.xz y data.tar.xz.
        local trabajo="$BUILD/deb/ar"
        rm -rf "$trabajo"
        mkdir -p "$trabajo"
        printf '2.0\n' > "$trabajo/debian-binary"
        local tar_opts=(--sort=name --owner=0 --group=0 --numeric-owner --mtime="@${SOURCE_DATE_EPOCH:-$(date +%s)}")
        tar -C "$staging/DEBIAN" "${tar_opts[@]}" -cJf "$trabajo/control.tar.xz" ./control ./md5sums
        tar -C "$staging" "${tar_opts[@]}" --exclude=./DEBIAN -cJf "$trabajo/data.tar.xz" ./usr
        (cd "$trabajo" && ar -rcD "$salida" debian-binary control.tar.xz data.tar.xz)
    fi
    echo "$salida"
}

construir_rpm() {
    paso "Paquete .rpm"
    if ! command -v rpmbuild >/dev/null 2>&1; then
        echo "Falta rpmbuild (instale rpm-build en Fedora o rpm-tools en Arch)." >&2
        return 1
    fi
    [[ $TARBALL_FRESCO -eq 1 ]] || construir_tarball >/dev/null
    local top="$BUILD/rpm"
    rm -rf "$top"
    mkdir -p "$top"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    cp "$TARBALL" "$top/SOURCES/"
    sed "s/@VERSION@/$VERSION/g" "$ROOT/packaging/rpm/melfpaint.spec" > "$top/SPECS/melfpaint.spec"
    rpmbuild --quiet -ba \
        --define "_topdir $top" \
        --define "_source_payload w9.gzdio" \
        --define "_binary_payload w9.gzdio" \
        "$top/SPECS/melfpaint.spec"
    find "$top/RPMS" "$top/SRPMS" -name '*.rpm' -exec cp {} "$DIST/" \;
    find "$DIST" -maxdepth 1 -name "$NAME-$VERSION-*.rpm" -print
}

construir_arch() {
    paso "Paquete de Arch Linux"
    if ! command -v makepkg >/dev/null 2>&1; then
        echo "Falta makepkg: el paquete de Arch se construye en Arch Linux o derivadas." >&2
        return 1
    fi
    [[ $TARBALL_FRESCO -eq 1 ]] || construir_tarball >/dev/null
    local dir="$BUILD/arch"
    rm -rf "$dir"
    mkdir -p "$dir"
    cp "$TARBALL" "$dir/"
    local suma
    suma="$(sha256sum "$TARBALL" | cut -d' ' -f1)"
    sed -e "s/@VERSION@/$VERSION/" -e "s/@SHA256@/$suma/" "$ROOT/packaging/arch/PKGBUILD" > "$dir/PKGBUILD"
    # -d: no exige que las dependencias estén instaladas en la máquina que construye.
    (cd "$dir" && PKGDEST="$DIST" SRCDEST="$dir" makepkg -f -d --noconfirm ${MELFPAINT_MAKEPKG_FLAGS:-})
    cp "$dir/PKGBUILD" "$DIST/PKGBUILD"
    find "$DIST" -maxdepth 1 -name "$NAME-$VERSION-*.pkg.tar.*" -print
}

objetivos=("$@")
[[ ${#objetivos[@]} -eq 0 ]] && objetivos=(all)

for objetivo in "${objetivos[@]}"; do
    case "$objetivo" in
        -h|--help) mostrar_ayuda; exit 0 ;;
        tarball) construir_tarball ;;
        deb) construir_deb ;;
        rpm) construir_rpm ;;
        arch) construir_arch ;;
        all)
            construir_tarball
            construir_deb
            construir_rpm || echo "Se omitió el .rpm." >&2
            construir_arch || echo "Se omitió el paquete de Arch." >&2
            ;;
        *) echo "Objetivo desconocido: $objetivo" >&2; mostrar_ayuda; exit 2 ;;
    esac
done
