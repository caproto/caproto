#!/bin/bash
set -e -x

source $TRAVIS_BUILD_DIR/.ci/epics-config.sh

if [ ! -e "$EPICS_BASE/built" ] 
then

    git clone https://github.com/epics-base/epics-base.git $EPICS_BASE
    ( cd $EPICS_BASE && git checkout $BASE );

    EPICS_HOST_ARCH=`sh $EPICS_BASE/startup/EpicsHostArch`

    case "$STATIC" in
    static)
        cat << EOF >> "$EPICS_BASE/configure/CONFIG_SITE"
SHARED_LIBRARIES=NO
STATIC_BUILD=YES
EOF
        ;;
    *) ;;
    esac

    make -C "$EPICS_BASE" -j2
    # get MSI for 3.14
    case "$BASE" in
    3.14*)
        echo "Build MSI"
        install -d "$HOME/msi/extensions/src"
        curl https://www.aps.anl.gov/epics/download/extensions/extensionsTop_20120904.tar.gz | tar -C "$HOME/msi" -xvz
        curl https://www.aps.anl.gov/epics/download/extensions/msi1-7.tar.gz | tar -C "$HOME/msi/extensions/src" -xvz
        mv "$HOME/msi/extensions/src/msi1-7" "$HOME/msi/extensions/src/msi"

        cat << EOF > "$HOME/msi/extensions/configure/RELEASE"
EPICS_BASE=$EPICS_BASE
EPICS_EXTENSIONS=\$(TOP)
EOF
        make -C "$HOME/msi/extensions"
        cp "$HOME/msi/extensions/bin/$EPICS_HOST_ARCH/msi" "$EPICS_BASE/bin/$EPICS_HOST_ARCH/"
        echo 'MSI:=$(EPICS_BASE)/bin/$(EPICS_HOST_ARCH)/msi' >> "$EPICS_BASE/configure/CONFIG_SITE"

        cat <<EOF >> ${EPICS_BASE}/CONFIG_SITE
MSI = \$(EPICS_BASE)/bin/\$(EPICS_HOST_ARCH)/msi
EOF

      ;;
    *) echo "Use MSI from Base"
      ;;
    esac

    touch $EPICS_BASE/built
else
    echo "Using cached epics-base!"
fi
