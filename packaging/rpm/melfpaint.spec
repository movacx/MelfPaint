Name:           melfpaint
Version:        @VERSION@
Release:        1%{?dist}
Summary:        Editor de imágenes de escritorio con capas, pinceles y formas
License:        GPL-3.0-or-later
URL:            https://github.com/movacx/MelfPaint
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  make
BuildRequires:  python3
Requires:       python3 >= 3.11
Requires:       (python3-pyside6 or python3-PySide6 or python3dist(pyside6))
Requires:       (python3-numpy or python3dist(numpy))
Requires:       hicolor-icon-theme
Recommends:     (python3-pillow or python3-Pillow)
Recommends:     (qt6-qttranslations or qt6-translations)

# Los archivos de la aplicación viven en /usr/share/melfpaint, fuera de
# site-packages; no se generan dependencias automáticas de Python.
%global __requires_exclude_from ^%{_datadir}/melfpaint/.*$
%global debug_package %{nil}

%description
MelfPaint es un editor de imágenes sencillo para Linux: selección,
recorte, cambiar tamaño y sesgar, girar y voltear, lápiz, relleno, texto,
borrador, selector de color, lupa, nueve pinceles, 23 formas editables,
paleta de colores, capas, reglas, cuadrícula y zoom.

%prep
%autosetup

%build
# Aplicación de Python pura: no hay nada que compilar.

%install
make install DESTDIR=%{buildroot} PREFIX=%{_prefix} PYTHON=%{__python3}
# %%license y %%doc instalan estos archivos en su lugar estándar.
rm -rf %{buildroot}%{_datadir}/licenses %{buildroot}%{_datadir}/doc/melfpaint

%files
%license LICENSE
%doc README.md
%{_bindir}/melfpaint
%{_datadir}/melfpaint/
%{_datadir}/applications/io.github.melfpaint.MelfPaint.desktop
%{_datadir}/metainfo/io.github.melfpaint.MelfPaint.metainfo.xml
%{_datadir}/mime/packages/io.github.melfpaint.MelfPaint.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.melfpaint.MelfPaint.svg

%changelog
* Thu Oct 01 2026 Herlin Chavarria <253316889+movacx@users.noreply.github.com> - @VERSION@-1
- Beta abierta: cinta de herramientas, selector de color, cuadro de texto editable,
  tamaños por herramienta, menú contextual de selección y paquetes para Linux.
