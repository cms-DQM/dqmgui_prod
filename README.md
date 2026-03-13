# CMS DQMGUI — Setup Guide

This guide covers how to set up a VM from scratch, install all dependencies, install the GUI, and run it.

---

## 1. Create the VM

Create a machine in OpenStack with **EL8 x86_64**. The `r2.xlarge` flavor should be enough.

---

## 2. Basic OS Configuration

Log in as `root` using the specified key pair, then run:

```bash
yum groupinstall "Development Tools" -y
dnf install -y libdrm libnsl libaio git gcc locmap-release
dnf install -y locmap
locmap --enable all
locmap --configure all
```

Reference: https://linux.web.cern.ch/almalinux/alma10/locmap/

---

## 3. Set Up LDAP (User Access)

Configure SSSD so that other users can log in to the machine:

```bash
curl -o /etc/sssd/conf.d/10_sssd.conf https://linux.web.cern.ch/docs/sssd.conf.example
OWNER=root  # EL8/EL9
chown "${OWNER}:${OWNER}" /etc/sssd/conf.d/10_sssd.conf
chmod 0600 /etc/sssd/conf.d/10_sssd.conf
restorecon /etc/sssd/conf.d/10_sssd.conf
rm /etc/sssd/conf.d/00_cern.conf
```

Then edit `/etc/sssd/conf.d/10_sssd.conf` and add or update the following line to restrict access to the appropriate e-group:

```
ldap_access_filter = (&(objectClass=user)(memberOf:1.2.840.113556.1.4.1941:=CN=cms-PPD-technical-support,OU=e-groups,OU=Workgroups,DC=cern,DC=ch))
```

Finally, enable and restart SSSD:

```bash
authselect select sssd with-silent-lastlog --force
systemctl enable sssd
systemctl stop sssd
systemctl start sssd
```

Reference: https://linux.web.cern.ch/docs/account-mgmt/

---

## 4. Install DQMGUI Build Dependencies

Log out from `root` and log back in with your personal account. Then switch to `root` to install packages globally:

```bash
sudo su
dnf install -y python3.8 pigz
alternatives --set python3 /usr/bin/python3.8
dnf install -y python38-pip
python3 -m pip install --upgrade pip
git clone https://github.com/cms-DQM/dqmgui_prod_deployment.git
dnf install -y $(cat dqmgui_prod_deployment/os_packages.txt)
rm -rf dqmgui_prod_deployment
```

---

## 5. Create the DQMGUI User and Installation Directory

Still as `root`, create a dedicated local user and set up the installation directory:

```bash
mkdir -p /data/srv
adduser dqmgui
chown -R dqmgui:dqmgui /data
```

---

## 6. Download DQMGUI Dependencies

Switch to the `dqmgui` user and clone the required repositories:

```bash
exit        # Back to your personal account
sudo su dqmgui

cd $HOME
git clone https://github.com/cms-DQM/dqmgui_prod_deployment.git
git clone https://github.com/cms-DQM/dqmgui_prod.git
cd dqmgui_prod_deployment
bash download_dependencies.sh do_download_dqmgui=0
```

> **Note:** The `do_download_dqmgui=0` flag skips downloading the DQMGUI source from the remote, because we will package it from the local clone in the next step. If you want to run the GUI without any local modifications, omit this flag and skip step 7.

---

## 7. Package DQMGUI from the Local Clone

Still as the `dqmgui` user, run the following from inside `dqmgui_prod_deployment/`:

```bash
repo=dqmgui
temp_dir=/tmp/$repo
mkdir -p "$temp_dir"
cp -r ../dqmgui_prod/* "$temp_dir"
rm -rf "$temp_dir/.git"   # Remove .git to speed up packaging
mkdir -p "$repo"
if [ -f "$repo/$repo.tar.gz" ]; then
    rm "$repo/$repo.tar.gz"
fi
tar -cf "$repo/$repo.tar.gz" --directory=/tmp "$repo" -I "pigz --best"
rm -rf "$temp_dir"
```

---

## 8. Build and Install

```bash
bash deploy_dqmgui.sh
```

---

## 9. Run the GUI

```bash
/data/srv/current/config/dqmgui/manage start "I did read documentation"
```

The GUI will be available inside the machine at:

```
http://localhost:8060/dqm/dev
```

If the machine's port is not reachable from outside, you can use SSH tunneling to access it from your local machine:

```bash
ssh -L 8060:localhost:8060 dqm-dev-machine2
```

---

## 10. Testing

### Offline Workflow

Download a ROOT file and upload it to the GUI using `visDQMUpload`:

```bash
# Example file available at:
# https://cmsweb.cern.ch/dqm/offline/data/browse/ROOT/OfflineData/Run2026/ZeroBias/0004016xx/DQM_V0001_R000401692__ZeroBias__Run2026A-PromptReco-v1__DQMIO.root

source /data/srv/current/apps/dqmgui/128/etc/profile.d/env.sh
visDQMUpload http://localhost:8060/dqm/dev DQM_V0001_R000401692__ZeroBias__Run2026A-PromptReco-v1__DQMIO.root
```

### Online Workflow

The online workflow is more involved. The GUI must have the collector configured. See `/data/srv/current/config/dqmgui/server-conf-online.py` for an example (the default configuration used during installation is `server-conf-dev.py`).

You will also need streamer files and a CMSSW client to push data to the local GUI. More details coming soon.

---

## 11. Development and Debugging

There are two types of changes you can make to the GUI: **compiled (C++)** and **Python**.

### Modifying the Python Code

You can edit the installed Python files directly without recompiling:

```
/data/srv/current/apps/dqmgui/128/
```

### Modifying the C++ Code

After modifying the source in your local `dqmgui_prod` clone, re-run step 7 to repackage, then reinstall only the DQMGUI components:

```bash
bash deploy_dqmgui.sh \
    do_preliminary_checks=0 \
    do_check_dependencies=0 \
    do_create_directories=0 \
    do_copy_env_file=0 \
    do_copy_wmcore_auth=0 \
    do_install_boost_gil=0 \
    do_install_gil_numeric=0 \
    do_install_rotoglup=0 \
    do_install_classlib=0 \
    do_compile_classlib=0 \
    do_extract_dmwm=0 \
    do_patch_dmwm=0 \
    do_install_dmwm=0 \
    do_install_root=0 \
    do_compile_root=0 \
    do_install_dqmgui=1 \
    do_compile_dqmgui=1 \
    do_install_yui=0 \
    do_install_extjs=0 \
    do_install_d3=0 \
    do_install_jsroot=0 \
    do_clean_crontab=0 \
    do_install_crontab=0
```

This skips all unchanged components and only rebuilds and reinstalls DQMGUI itself.
