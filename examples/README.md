# Deploying amazee.ai with K0rdent
This guide assumes a base level of experience with helm, kubernetes, and k0rdent. More information on each can be found in their respective documentation. Included you will find templates and charts required for a fully functional amazee.ai LLM credential provisioning system. The examples are based on a deployment to AWS, but the system will run on any infrastructure.
### Setting up
Begin by setting up your k0rdent management system. You can follow the [quickstart guide](https://docs.k0rdent-enterprise.io/latest/quickstarts/) and then use the `clusterctl move --to-kubeconfig=target-kubeconfig.yaml` command to use the included mothership config, or use your own management cluster. If deploying to AWS, the included `aws-cluster-identity.yaml` is sufficient for credentials used for cluster management, simply set the appropriate values in the `Secret` before applying.
In order to make use of the charts and default values in the `amazeeai-k0rdent-catalog`, it will need to be applied to the controller.
```bash
kubectl apply -f charts/amazeeai-k0rdent-catalog/templates/helm-repository.yaml -n kcm-system
```
This sets up the necessary helm repository to pull dependent charts.
Next, configure service templates for amazee.ai and LiteLLM
```bash
kubectl apply -f serviceTemplates/litellm/litellm-serviceTemplate.yaml
kubectl apply -f serviceTemplates/amazee-ai/amazee-ai-serviceTemplate.yaml
```
You can verify the status of the service templates with
```bash
kubectl get servicetemplates -A
```
Once the service templates show as ready, make modifications and apply the child cluster deployments
```bash
kubectl apply -f clusters/development/amazeeai-ch2.yaml # Set up LiteLLM
kubectl apply -f clusters/development/amazeeai-global.yaml # Set up provisioning and dashboarding
```
For the global provisioning system, it is recommended that you use a managed database service, but if you wish to deploy one as part of the k0rdent setup you can do so in the `postgresql` block by setting `enabled: true` and defining your preferred values. For more details on the amazee.ai helm chart, see [the dedicated README](https://github.com/amazeeio/amazee.ai/tree/main/helm).
The LiteLLM system is self contained, but requires credentials for connecting to configured Amazon Bedrock LLMs. If you are deploying your own models locally, then the AWS credentials may not be necessary.