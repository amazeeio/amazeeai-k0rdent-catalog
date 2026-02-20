# AmazeeAI k0rdent Catalog

This repository contains the [k0rdent](https://k0rdent.io/) templates and Helm charts for provisioning and managing [amazee.ai](https://amazee.ai/) infrastructure.

## Usage

All charts are published as OCI artifacts to the GitHub Container Registry (`ghcr.io/amazeeio`). 

To pull a specific chart using Helm:

```bash
helm pull oci://ghcr.io/amazeeio/amazeeai-k0rdent-catalog/charts/<chart-name> --version <version>
```
