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
    {{- $valuesHash := toYaml .Values.controlPlane | sha256sum | trunc 8 -}}
    {{- printf "%s-cp-mt-%s-%s" $clusterName $version $valuesHash | trunc 63 | trimSuffix "-" -}}
{{- end }}
{{/*
--- END CUSTOMIZATION ---
*/}}

{{/*
--- START CUSTOMIZATION: Do not remove ---
Worker AWSMachineTemplate Name (Chart Version + Worker Values Hash)
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

{{- define "encryption-config.fullpath" -}}
    {{- include "encryption-config.dir" . }}/{{- include "encryption-config.file" . }}
{{- end }}

{{- define "encryption-config.dir" -}}
    /var/lib/k0s/encryption
{{- end }}

{{- define "encryption-config.hash" -}}
    {{- if .Values.encryption.configSecret.hash -}}
    {{- .Values.encryption.configSecret.hash -}}
    {{- else -}}
    {{- $secretName := .Values.encryption.configSecret.name -}}
    {{- $secretKey := default "config" .Values.encryption.configSecret.key -}}
    {{- if $secretName -}}
    {{- $secret := lookup "v1" "Secret" .Release.Namespace $secretName -}}
    {{- if and $secret $secret.data (hasKey $secret.data $secretKey) -}}
    {{- sha256sum (b64dec (index $secret.data $secretKey)) | trunc 8 -}}
    {{- end -}}
    {{- end -}}
    {{- end -}}
{{- end }}

{{- define "encryption-config.file" -}}
    {{- $hash := include "encryption-config.hash" . | trim -}}
    {{- if $hash -}}
    config-{{ $hash }}.yaml
    {{- else -}}
    config.yaml
    {{- end -}}
{{- end }}

{{- define "audit-policy.dir" -}}
    /var/lib/k0s/audit
{{- end }}
{{- define "audit-policy.file" -}}
    {{- if .Values.audit.policyRef.hash -}}
    policy-{{ .Values.audit.policyRef.hash }}.yaml
    {{- else -}}
    policy.yaml
    {{- end -}}
{{- end }}
{{- define "audit-policy.fullpath" -}}
    {{- include "audit-policy.dir" . }}/{{- include "audit-policy.file" . }}
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
