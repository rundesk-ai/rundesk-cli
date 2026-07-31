---
id: CAT
name: A catalog of skills
last_verified: 2026-07-31
---

## What this is

A versioned repository that makes one or more complete skills available in Rundesk's shared
library. The repository moves and is removed as one catalog while each skill is granted separately.

## Why it exists

- Owners install maintained skills without copying packages by hand.
- Every installed skill has a knowable source and version.
- Catalog changes cannot replace owner-authored skills or break agent grants.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-CAT-1 | A catalog declares its name, version, and complete skill packages in one manifest | `a manifest declares its version and every complete skill`, `a version must be complete semantic versioning` |
| ✅ | R-CAT-2 | A catalog is completely validated and previewed before installation changes anything | `a future manifest format is refused`, `a skill path cannot leave the repository`, `a skill no brain would index is refused`, `an archive cannot write outside the unpack directory`, `installing first previews the repository and changes nothing` |
| ✅ | R-CAT-3 | Installing a catalog exposes every declared skill without granting any automatically | `installing exposes every skill without granting any`, `a catalog skill can be granted and revoked through the library`, `confirming installs the repository without granting a skill` |
| ✅ | R-CAT-4 | Every installed catalog reports its repository source and declared version | `installed provenance names the repository and version`, `provenance that disagrees with the installed version is refused`, `installed catalogs show version source and skill count` |
| ✅ | R-CAT-5 | A catalog never replaces or removes owner-authored skill content | `owner authored skill with same name refuses install`, `removing takes only the catalog and its library links`, `removing without yes previews and changes nothing` |
| ✅ | R-CAT-6 | A retired built-in skill can move to catalog ownership without breaking its grants | `a retired built in is adopted without breaking its grant`, `optional external skills are not rundesk built ins` |
| ✅ | R-CAT-7 | A newer repository version replaces the installed catalog as one unit | `a newer repository version replaces every installed skill` |
| ✅ | R-CAT-8 | A failed catalog update leaves the previously working version available | `a failed update leaves the working version`, `a failure after activation rolls back files links and provenance`, `failed adoption restores the retired built in` |
| ✅ | R-CAT-9 | Updating or removing a catalog cannot remove a skill while any agent holds it | `an update cannot remove a granted skill`, `removing refuses while one of its skills is granted`, `updating tells the catalog which skills are granted` |

## Open questions

- When curated catalogs should update automatically rather than only when explicitly requested.
