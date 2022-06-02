# CMS DQMGUI

## How to test PR 
For example, we need to test PR to GUI. Then, merge PR to the dev128 branch and create a tag from this branch.
Setup enviroment:
```
ssh cmsdev20.cern.ch
git clone git@github.com:cms-sw/cmsdist -b comp_gcc630
git clone git@github.com:cms-sw/pkgtools -b V00-33-XX
```
update cmsdist/dqmgui.spec to use tag from dev128 branch and change the tag number (first line). Compile, build:
```
./pkgtools/cmsBuild --repo comp -a slc7_amd64_gcc630 -i w -j 10 build dqmgui
```
probably, after this it is possible to move executables to P5 machine.
This will create RPM file in the folder like:
```
w/BUILD/slc7_amd64_gcc630/cms/dqmgui/9.7.6-806fc9e67463bf3883214edfa77e3b6f
```
To extract:
```
rpm2cpio myrpmfile.rpm | cpio -idmv
```
Then at a srv machine we can do something like:
```
cd /data/srv
cd ./stop_everything
cp w/slc7_amd64_gcc630/cms/dqmgui/9.7.6-806fc9e67463bf3883214edfa77e3b6f/128/bin/visDQM* /data/srv/HG2206c/sw/slc7_amd64_gcc630/cms/dqmgui/9.7.4/128/bin/.
```
Then 
```
cd /dqmdata/dqm/repository/original/OnlineData/00035xxxx/0003525xx/
cp DQM_V0001_HLTpb_R000352572.root DQM_V0002_HLTpb_R000352572.root
cp DQM_V0001_SiStrip_R000352572.root.dqminfo DQM_V0002_SiStrip_R000352572.root.dqminfo
```
modify the path in `DQM_V0002_SiStrip_R000352572.root.dqminfo` and feed the file to indexer, check logs:
```
cp DQM_V0002_SiStrip_R000352572.root.dqminfo /dqmdata/dqm/agents/import-srv-c2f11-29-04/.
nano /data/srv/logs/dqmgui/online/agent-import-128-20220602-srv-c2f11-29-04.log
```

## Update Offline DQM GUI:  
Make and merge a PR into branch index128. Create a tag in dqmgui repo. Change GUI version in cmsdist (first line): 
`https://github.com/cms-sw/cmsdist/blob/comp_gcc630/dqmgui.spec` in branch comp_gcc630. 
Ask for the new version (cmsdist and dmwm/deployment PRs) to be added to the next CMSWEB release. 
Eg.: https://gitlab.cern.ch/cms-http-group/doc/issues/207  
If you need a release urgently, ask for it to be tagged with an HG tag: (the new Lina) muhammad.imran@cern.ch  dmwm/deployment PRs can be merged as patches during deployment (Online)

## Continuous integration

[Jenkins server](https://cms-dqmgui-ci.web.cern.ch/job/dqmgui-github/) uses `Jenkinsfile` to build.
Slave `dqmgui-ci-worker` is configured to use the docker image produced [here](https://gitlab.cern.ch/rovere/dqmgui-ci-worker)


