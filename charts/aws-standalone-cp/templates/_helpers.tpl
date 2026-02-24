{{- define "cluster.name" -}}
    {{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
--- START CUSTOMIZATION: Do not remove ---
Control Plane AWSMachineTemplate Name (Chart Version + CP Values Hash)
*/}}
{{- define "awsmachinetemplate.controlplane.name" -}}
    {{- /* Truncate the cluster name to 40 chars to guarantee room for the version and hash */ -}}
    {{- $clusterName := include "cluster.name" . | trunc 40 | trimSuffix "-" -}}
    {{- $version := replace "." "-" .Chart.Version -}}
    {{- $valuesHash := toYaml .Values.controlPlane.machineSpec | sha256sum | trunc 8 -}}
    {{- printf "%s-cp-mt-%s-%s" $clusterName $version $valuesHash | trunc 63 | trimSuffix "-" -}}
{{- end }}
{{/*
--- END CUSTOMIZATION ---
*/}}

{{/*
--- START CUSTOMIZATION: Do not remove ---
Worker AWSMachineTemplate Name (Chart Version + CP Values Hash)
*/}}
{{- define "awsmachinetemplate.worker.name" -}}
    {{- /* Truncate the cluster name to 40 chars to guarantee room for the version and hash */ -}}
    {{- $clusterName := include "cluster.name" . | trunc 40 | trimSuffix "-" -}}
    {{- $version := replace "." "-" .Chart.Version -}}
    {{- $valuesHash := toYaml .Values.worker | sha256sum | trunc 8 -}}
    {{- printf "%s-worker-mt-%s-%s" $clusterName $version $valuesHash | trunc 63 | trimSuffix "-" -}}
{{- end }}
{{/*
--- END CUSTOMIZATION ---
*/}}

{{- define "k0scontrolplane.name" -}}
    {{- include "cluster.name" . }}-cp
{{- end }}

{{- define "k0sworkerconfigtemplate.name" -}}
    {{- include "cluster.name" . }}-machine-config
{{- end }}

{{- define "machinedeployment.name" -}}
    {{- include "cluster.name" . }}-md
{{- end }}

{{- define "authentication-config.fullpath" -}}
    {{- include "authentication-config.dir" . }}/{{- include "authentication-config.file" . }}
{{- end }}

{{- define "authentication-config.dir" -}}
    /var/lib/k0s/auth
{{- end }}

{{- define "authentication-config.file" -}}
    {{- if .Values.auth.configSecret.hash -}}
    config-{{ .Values.auth.configSecret.hash }}.yaml
    {{- else -}}
    config.yaml
    {{- end -}}
{{- end }}

{{/*
--- START CUSTOMIZATION: Do not remove ---
Helm resource-policy annotation for underlying CAPI resources.
This ensures CAPI's cascading deletion handles infrastructure cleanup, not Helm.
*/}}
{{- define "aws-standalone.keepPolicy" -}}
{{- if default true .Values.keepResources -}}
helm.sh/resource-policy: keep
{{- end -}}
{{- end -}}
{{/* --- END CUSTOMIZATION */}}
