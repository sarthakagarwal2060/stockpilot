{{- define "stockpilot.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "stockpilot.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels for one component: include "stockpilot.selectorLabels" (list . "backend") */}}
{{- define "stockpilot.selectorLabels" -}}
{{- $ctx := index . 0 -}}
app.kubernetes.io/name: {{ $ctx.Chart.Name }}
app.kubernetes.io/instance: {{ $ctx.Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end -}}

{{- define "stockpilot.backendName" -}}{{ include "stockpilot.fullname" . }}-backend{{- end -}}
{{- define "stockpilot.frontendName" -}}{{ include "stockpilot.fullname" . }}-frontend{{- end -}}
{{- define "stockpilot.postgresName" -}}{{ include "stockpilot.fullname" . }}-postgres{{- end -}}
{{- define "stockpilot.dbSecretName" -}}{{ include "stockpilot.fullname" . }}-db{{- end -}}

{{- define "stockpilot.dbHost" -}}
{{- if .Values.postgres.enabled -}}{{ include "stockpilot.postgresName" . }}{{- else -}}{{ required "postgres.externalHost is required when postgres.enabled=false" .Values.postgres.externalHost }}{{- end -}}
{{- end -}}

{{/*
DB password: explicit value > existing Secret (so upgrades keep it) > new random value.
*/}}
{{- define "stockpilot.dbPassword" -}}
{{- if .Values.postgres.password -}}
{{- .Values.postgres.password -}}
{{- else -}}
{{- $existing := lookup "v1" "Secret" .Release.Namespace (include "stockpilot.dbSecretName" .) -}}
{{- if and $existing (index $existing.data "password") -}}
{{- index $existing.data "password" | b64dec -}}
{{- else -}}
{{- randAlphaNum 24 -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "stockpilot.podSecurity" -}}
allowPrivilegeEscalation: false
runAsNonRoot: true
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
