%if 0%{?rhel} <= 5
%define __python /usr/bin/python26
%endif
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Name: cloud-init-foreman
Version: %{_pkg_version}
Release: %{_pkg_release}%{?dist}
Summary: Foreman module for cloudinit
Group: System Environment/Base
License: GPL
Source0: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root
BuildArch: noarch

%if 0%{?rhel} >= 6
Requires: python2
BuildRequires: python2-devel
%else
Requires: python26
BuildRequires: python26-devel
%endif
Requires: facter
Requires: cloud-init
BuildRequires: redhat-rpm-config

%define CLOUDINITDIR %{python_sitelib}/cloudinit

%description
This package contains cloudinit module which registers the host in foreman.
 
%prep
%setup -q

%build

%install
[ %{buildroot} != / ] && rm -rf %{buildroot}
mkdir -p %{buildroot}/%{CLOUDINITDIR}/config/
install -m 644 cc_foreman.py %{buildroot}/%{CLOUDINITDIR}/config/cc_foreman.py

%clean
[ %{buildroot} != / ] && rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
%dir %{CLOUDINITDIR}
%dir %{CLOUDINITDIR}/config
%{CLOUDINITDIR}/config/cc_foreman.py
%{CLOUDINITDIR}/config/cc_foreman.pyo
%{CLOUDINITDIR}/config/cc_foreman.pyc

%post
# if "- foreman" is not cloud.cfg already quit silently
grep -q "^ - foreman" /etc/cloud/cloud.cfg || sed -i /etc/cloud/cloud.cfg -e'/^ - puppet/i\ - foreman'

%postun
# remove foreman
sed -i /etc/cloud/cloud.cfg -e'/^ - foreman/d'

%preun
/bin/true

%changelog
* Fri May 11 2018 Gavin Williams <gavin.williams@weareact.com> 0.4-3
- Updates to disable SSL verification, as default behaviour changed in rhbz#1490392
- Standardise on using 'makeRequest' for url requests
* Tue Mar 28 2017 Gavin Williams <gavin.williams@weareact.com> 0.4-2
- Further updates to support Puppet 4 paths, and improve Foreman handling
* Thu Nov 17 2016 Gavin Williams <gavin.williams@weareact.com> 0.4-1
- Updates to support latest CloudInit
* Wed Jul 18 2012 Jan van Eldik <Jan.van.Eldik@cern.ch> 0.3-2
- fixes to build on RHEL5
* Wed Jul 18 2012 <tkarasek at cern.ch> 0.3-1
- rpm install/remove now adds/removes " - foreman" to/from cloud.cfg
* Fri Jul 06 2012 <tkarasek at cern.ch> 0.2-1
- fixup of hostname resolve
* Mon Jun 25 2012 <tkarasek at cern.ch> 0.1-1
- initial import 

