PACKAGE_NAME=cloud-init-foreman
VERSION=0.4
RELEASE=1
TARBALL=$(PACKAGE_NAME)-${VERSION}.tar.gz
SOURCES=cc_foreman.py cloud-init-foreman.spec
.PHONY: clean

pkg: 
	tar -czf $(TARBALL) --transform 's,^,${PACKAGE_NAME}-${VERSION}/,'  $(SOURCES)

rpm: pkg
	rpmbuild --define "_pkg_version ${VERSION}" --define "_pkg_release ${RELEASE}" -ta $(TARBALL) --clean

clean:
	rm -rf $(TARBALL)

