{{- define "agentic-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentic-app.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "agentic-app.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "agentic-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "agentic-app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agentic-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "agentic-app.apiName" -}}
{{- printf "%s-api" (include "agentic-app.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentic-app.uiName" -}}
{{- printf "%s-ui" (include "agentic-app.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentic-app.secretName" -}}
{{- if .Values.api.existingSecret -}}
{{- .Values.api.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "agentic-app.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
