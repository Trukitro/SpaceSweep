# winget manifests

Manifests for `Trukitro.SpaceSweep`, ready to submit to [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs).

For a new version:

1. Publish the GitHub release with `SpaceSweepSetup.exe`.
2. Copy `manifests/t/Trukitro/SpaceSweep/<old>` to a new version folder, then update `PackageVersion`, `InstallerUrl`, `InstallerSha256` (`Get-FileHash dist\SpaceSweepSetup.exe`), `ReleaseDate` and `ReleaseNotesUrl`.
3. Check it: `winget validate --manifest packaging\winget\manifests\t\Trukitro\SpaceSweep\<version>`
4. Submit: copy the version folder into a fork of winget-pkgs at the same path and open a pull request (or use `wingetcreate submit`).

Once accepted, people can install it with:

```powershell
winget install Trukitro.SpaceSweep
```
