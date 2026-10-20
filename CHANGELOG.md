## [1.9.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.8.0...v1.9.0) (2026-10-20)


### Features

* [sc-20634] add pass-through options for platform ros build ([#18](https://github.com/Greenroom-Robotics/platform_cli/issues/18)) ([aaca0d0](https://github.com/Greenroom-Robotics/platform_cli/commit/aaca0d00dc3a1e5e285b03f0445c0235c1419da1))
* add ability to build package deps ([f4592d7](https://github.com/Greenroom-Robotics/platform_cli/commit/f4592d70747e9d0ea2270b7b944e05ba7c747205))
* add ability to specify extra cmake args ([#16](https://github.com/Greenroom-Robotics/platform_cli/issues/16)) ([39abe73](https://github.com/Greenroom-Robotics/platform_cli/commit/39abe73605eddc0b5b8e9111c810d9761237dd04))
* bump and commit pixi.toml in deb release ([#22](https://github.com/Greenroom-Robotics/platform_cli/issues/22)) ([856112d](https://github.com/Greenroom-Robotics/platform_cli/commit/856112d6111704729dee6f07b52c26a037058673))
* name package in release commit subject ([#24](https://github.com/Greenroom-Robotics/platform_cli/issues/24)) ([de2e32d](https://github.com/Greenroom-Robotics/platform_cli/commit/de2e32de5734016e2228acce10022b1d962bfdf1))
* single release commit for multi-package releases ([#26](https://github.com/Greenroom-Robotics/platform_cli/issues/26)) ([f98e937](https://github.com/Greenroom-Robotics/platform_cli/commit/f98e9371f82c0b7fc90a788936f0ea0c5be06c8d))


### Bug Fixes

* bump and commit pixi.toml only in release job, not build legs ([#23](https://github.com/Greenroom-Robotics/platform_cli/issues/23)) ([7c37e11](https://github.com/Greenroom-Robotics/platform_cli/commit/7c37e1194793b8c70103d58961a6a3e64bd655fe))
* install pip rosdeps without sudo ([#25](https://github.com/Greenroom-Robotics/platform_cli/issues/25)) ([013d564](https://github.com/Greenroom-Robotics/platform_cli/commit/013d564dcf09d6d716194b60bfaa4b1e183437ab))
* old defaults ([3480ccb](https://github.com/Greenroom-Robotics/platform_cli/commit/3480ccba4d78b59bb7911544781f1cc9de93a0dd))
* warn instead of failing on pixi.toml without [package] table ([#28](https://github.com/Greenroom-Robotics/platform_cli/issues/28)) ([35460d3](https://github.com/Greenroom-Robotics/platform_cli/commit/35460d332a7d9373866d08c3eedbb90e1141a98d))

## [1.8.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.7.2...v1.8.0) (2026-03-04)


### Features

* add --secrets to `platform release create` ([33ff38f](https://github.com/Greenroom-Robotics/platform_cli/commit/33ff38f2940cf115e520adf376c928341156c4c1))
* export compile commands on build ([#15](https://github.com/Greenroom-Robotics/platform_cli/issues/15)) ([f652010](https://github.com/Greenroom-Robotics/platform_cli/commit/f6520105b5dfbb882f11a87ce3af754a38d2dd8d))


### Bug Fixes

* filter empty package strings ([657033a](https://github.com/Greenroom-Robotics/platform_cli/commit/657033aab8cb12575dfebf5d0489c4253bb613ab))

## [1.7.2](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.7.1...v1.7.2) (2025-11-18)


### Bug Fixes

* actually pass on nocheck to debuild ([5da21a6](https://github.com/Greenroom-Robotics/platform_cli/commit/5da21a6595561cec8c743319f2a89bb10600a8d4))
* add multi-package support ([32358c4](https://github.com/Greenroom-Robotics/platform_cli/commit/32358c4068887a3379ddf5725b5158bd206eed3c))
* forever the janitor ([6306a4e](https://github.com/Greenroom-Robotics/platform_cli/commit/6306a4ee304207407d1cafed287996c69be96a5b))
* make enum str/val the same ([0e3c5c5](https://github.com/Greenroom-Robotics/platform_cli/commit/0e3c5c5c5e4d4a2a3124d0eb480328b4a68a0c85))
* pass GPU env var in as a build arg ([7b7995f](https://github.com/Greenroom-Robotics/platform_cli/commit/7b7995fd197acbdeae888eb7247acb4c994771e7))

## [1.7.1](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.7.0...v1.7.1) (2025-05-09)


### Bug Fixes

* ignore changes to _params.py files ([eec5268](https://github.com/Greenroom-Robotics/platform_cli/commit/eec52688f1e181f8e98bbeba1d88f861d8cdbbc8))

## [1.7.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.6.0...v1.7.0) (2025-05-08)


### Features

* add `branches` option to `platform release create` ([0ec2282](https://github.com/Greenroom-Robotics/platform_cli/commit/0ec2282fdabc07187306d556c91fc75573c94802))


### Bug Fixes

* add console output to colcon test ([30fadf3](https://github.com/Greenroom-Robotics/platform_cli/commit/30fadf3100f97a271e0522212195dd239152c6e1))
* attempt to fix stdout disappearing while building ([4d44d41](https://github.com/Greenroom-Robotics/platform_cli/commit/4d44d417fe5b7363caabe2a98553b20ffc23dc70))
* correct way to specify cores ([3f201d1](https://github.com/Greenroom-Robotics/platform_cli/commit/3f201d1cd59775f0df1299b6451c61a42b274117))
* maybe this is it ([f018556](https://github.com/Greenroom-Robotics/platform_cli/commit/f018556b08e5400f8e780cb16e3dd2f44a651d81))
* retest_until_pass 2 times by default ([67fb50b](https://github.com/Greenroom-Robotics/platform_cli/commit/67fb50b51ec28d77242ffdabcecb145b3330161e))
* throttle the job number on buildjet arm runners ([112d6f3](https://github.com/Greenroom-Robotics/platform_cli/commit/112d6f368bfca9e635b6a4ab4e4bfe156532eb0a))

## [1.6.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.5.0...v1.6.0) (2024-12-10)


### Features

* Post Build tagging in Semantic Release [sc-12927] ([#9](https://github.com/Greenroom-Robotics/platform_cli/issues/9)) ([3beb889](https://github.com/Greenroom-Robotics/platform_cli/commit/3beb88930a1b5f4835ba175d1b4b20dc69861ee6))


### Bug Fixes

* also set distro on the update command ([1170d28](https://github.com/Greenroom-Robotics/platform_cli/commit/1170d2851936c396a567e1bc98a1120d6d2e1c0d))
* hack to bring iron back from the dead ([c92aedc](https://github.com/Greenroom-Robotics/platform_cli/commit/c92aedc03f9cf93cd2278ceb11e478cd025575a6))

## [1.5.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.4.0...v1.5.0) (2024-11-18)


### Features

* workspace functionality aka russ's super cool secret branch ([#7](https://github.com/Greenroom-Robotics/platform_cli/issues/7)) ([b4cd70b](https://github.com/Greenroom-Robotics/platform_cli/commit/b4cd70bf9107ca9019e34326abfb68eb1cb8bf04))


### Bug Fixes

* don't call self, use functions instead ([2a1d993](https://github.com/Greenroom-Robotics/platform_cli/commit/2a1d993930ba735eac33601a36faeef75ceccc3c))
* process calling now sends SIGINT, SIGTERM correctly ([c51d487](https://github.com/Greenroom-Robotics/platform_cli/commit/c51d487bb4544ddf6de13d677293997660130668))
* typing issues ([#8](https://github.com/Greenroom-Robotics/platform_cli/issues/8)) ([5af5f83](https://github.com/Greenroom-Robotics/platform_cli/commit/5af5f83c0ddd5b0e2928f3302e854f250df11f53))
* update Dockerfile assets ([8653dd6](https://github.com/Greenroom-Robotics/platform_cli/commit/8653dd6b22d8f6a304f9197e875c949dded0ad5e))
* use merge strategy ([b1d90dd](https://github.com/Greenroom-Robotics/platform_cli/commit/b1d90ddc64b49e95e4405fcdc837dca22e027f88))

## [1.4.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.3.3...v1.4.0) (2024-06-12)


### Features

* add ros_distro support to release ([3529d5d](https://github.com/Greenroom-Robotics/platform_cli/commit/3529d5dcf4db6ccdcc76440d56f5c01abd6434c8))

## [1.3.3](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.3.2...v1.3.3) (2024-03-01)


### Bug Fixes

* add PACKAGE_DIR ([60c0c45](https://github.com/Greenroom-Robotics/platform_cli/commit/60c0c45af812a80b9c621701560123fc7880b1a9))
* mount packages into the same location ([c4b001a](https://github.com/Greenroom-Robotics/platform_cli/commit/c4b001a30faf885724024bc873fcd81f2150e570))

## [1.3.2](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.3.1...v1.3.2) (2024-02-14)


### Bug Fixes

* only mount packages in the package_dir into the docker container ([250a9b7](https://github.com/Greenroom-Robotics/platform_cli/commit/250a9b790037278f9e31bddffe382096b4b14a0d))

## [1.3.1](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.3.0...v1.3.1) (2024-01-14)


### Bug Fixes

* only watch pythong and cpp files ([b72239b](https://github.com/Greenroom-Robotics/platform_cli/commit/b72239b1be09dc503a6134c369e2c581852cfa10))

## [1.3.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.2.3...v1.3.0) (2023-12-12)


### Features

* add a `plaform ros run` script ([c4bfbed](https://github.com/Greenroom-Robotics/platform_cli/commit/c4bfbedecaadf0b661f5acfbabc8f59674b7d023))

## [1.2.3](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.2.2...v1.2.3) (2023-10-24)


### Bug Fixes

* add support for processes when using `--watch` ([723f917](https://github.com/Greenroom-Robotics/platform_cli/commit/723f9175937b896e3b1afd8ae88dbe8e7bdcaa4e))

## [1.2.2](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.2.1...v1.2.2) (2023-10-24)


### Bug Fixes

* remove `process=True` from build ([b3280fa](https://github.com/Greenroom-Robotics/platform_cli/commit/b3280fae13831db2900fd06b365cbe1d3474b410))

## [1.2.1](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.2.0...v1.2.1) (2023-10-24)


### Bug Fixes

* update ci process ([5b8b262](https://github.com/Greenroom-Robotics/platform_cli/commit/5b8b262b14919a8c85564de8dca84b3b4ba92914))

## [1.2.0](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.1.0...v1.2.0) (2023-10-24)


### Features

* add --build and --watch flags to ros test and launch ([ce05eb6](https://github.com/Greenroom-Robotics/platform_cli/commit/ce05eb620d5fd931f140169994c3523fa71ea759))
* add --sparse option to apt clone and add ([71e3def](https://github.com/Greenroom-Robotics/platform_cli/commit/71e3def7b9f1dfea266c7536d3912ef077e59443))
* add --watch option to `platform ros build` ([14992dd](https://github.com/Greenroom-Robotics/platform_cli/commit/14992dd43b39c35beba1d23c0f2c3a90a44907fc))
* add package-dir argument to release ([63fc640](https://github.com/Greenroom-Robotics/platform_cli/commit/63fc64022615a84d1e3182c7a754848e79e0cdad))
* update Dockerfile to iron ([613a028](https://github.com/Greenroom-Robotics/platform_cli/commit/613a028e77f949d886c906c30f011ed0fb81ac46))


### Bug Fixes

* add exception if API_TOKEN_GITHUB not set ([e4db930](https://github.com/Greenroom-Robotics/platform_cli/commit/e4db9304552011f3bf2a579a005ba82d3d47b15e))
* also upload the debian debugsym ddeb to gh release ([aa89f48](https://github.com/Greenroom-Robotics/platform_cli/commit/aa89f48127fb5ced703408caaffeb585889aa63a))
* do not force push ([880e819](https://github.com/Greenroom-Robotics/platform_cli/commit/880e81975a037c7d6737e2d1a678f0ff20098252))
* don't have colcon create log when finding packages ([2b3f026](https://github.com/Greenroom-Robotics/platform_cli/commit/2b3f026c75ddaddfe960897b92c0a155c43f6998))
* ensure git lfs hooks have been installed ([a7e8278](https://github.com/Greenroom-Robotics/platform_cli/commit/a7e8278d5e34ddc885d629d788d66374227ecf66))
* finding debs when debug_files is false ([42ee412](https://github.com/Greenroom-Robotics/platform_cli/commit/42ee4120acf10523228643c3ceb93578b7ca0b4e))
* use ProcessWatcher to handle `--watch` ([d81b99d](https://github.com/Greenroom-Robotics/platform_cli/commit/d81b99dbdf0fd592d6cdad7e139fb24c1da7a611))

## [1.0.1](https://github.com/Greenroom-Robotics/platform_cli/compare/v1.0.0...v1.0.1) (2022-11-20)


### Bug Fixes

* add __init__.py to git asset list ([fde2453](https://github.com/Greenroom-Robotics/platform_cli/commit/fde24539e8e44e6d497306864f327b9b98949173))
* add --without-hashes to fix https://github.com/python-poetry/poetry/issues/3472 ([93ca1ec](https://github.com/Greenroom-Robotics/platform_cli/commit/93ca1ecd0bc495ef4dfeb62b73e410763c8ae222))
* raise errors on build and test ([05d148c](https://github.com/Greenroom-Robotics/platform_cli/commit/05d148c0f6837cf1c9b5183ffe233ffada5c23c8))

## 1.0.0 (2022-09-18)


### Features

* add entrypoint ([9ce834c](https://github.com/Greenroom-Robotics/platform_cli/commit/9ce834cad55d039ac25dee1daa48b369baff5169))
* add more stuff ([34137b6](https://github.com/Greenroom-Robotics/platform_cli/commit/34137b6fdc8abca034fa5735fba97669f0d79dba))
* add release ci ([8c20153](https://github.com/Greenroom-Robotics/platform_cli/commit/8c201532cbbb950480af4134869bbf058995be6f))
* improve cli with double-dash ([dd62f5a](https://github.com/Greenroom-Robotics/platform_cli/commit/dd62f5a65d89e0f5773cdc1215395f242f2ef0d4))
* initial commit ([7758798](https://github.com/Greenroom-Robotics/platform_cli/commit/775879853f8a38465bcaaf978fad28051d297001))
* make glbober recursive ([ea95821](https://github.com/Greenroom-Robotics/platform_cli/commit/ea9582146ce9dd5b0dffe25c5ef591e8217c50de))
* remove docker build ([5033325](https://github.com/Greenroom-Robotics/platform_cli/commit/50333250dbe30ac215d7543608939890f54c318c))
* simplify ([2a921c7](https://github.com/Greenroom-Robotics/platform_cli/commit/2a921c7928ade04a8c394f51f7db2c1f99d1a9e7))


### Bug Fixes

* add click ([8e2bbcb](https://github.com/Greenroom-Robotics/platform_cli/commit/8e2bbcb014fc32bfd90c60c1cb7fc3a8a212561d))
* always run opt/greenroom/package ([a4a292d](https://github.com/Greenroom-Robotics/platform_cli/commit/a4a292db45b80891754d2febb64bc0c5e96b22bb))
* change to PLATFORM_MODULE ([3c28227](https://github.com/Greenroom-Robotics/platform_cli/commit/3c28227d05a9272e23e64cea654b139a6e80eab0))
* flatten ([3b8906b](https://github.com/Greenroom-Robotics/platform_cli/commit/3b8906bd2214d020fddca929c6447eb7e99eee68))
* maybe ([0184fd8](https://github.com/Greenroom-Robotics/platform_cli/commit/0184fd8e64db2ea78d17f98ce62c5c6339e066b6))
* rm requirements ([4cfba7f](https://github.com/Greenroom-Robotics/platform_cli/commit/4cfba7f1d82f1578a002321d9eb92b698e31b861))
* test only ubuntu ([47dba6b](https://github.com/Greenroom-Robotics/platform_cli/commit/47dba6baa3e2f19887bc5966e9d00268405bb8dc))
* use /bin/bash ([3aed4e0](https://github.com/Greenroom-Robotics/platform_cli/commit/3aed4e0bc75862eac4253faf9ef760a958457e40))
* use pip3 ([f03af69](https://github.com/Greenroom-Robotics/platform_cli/commit/f03af69493ef4e3a5e016aee9f7f8aa9750e3411))
* venv warning in stdout ([a0a8414](https://github.com/Greenroom-Robotics/platform_cli/commit/a0a84140a8117b29a07d46e9c2cc6607d9ea66a0))
