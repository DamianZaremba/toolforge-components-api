---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: "{{ .Release.Name }}-certificate"
  labels:
    name: "components-api"
spec:
  commonName: "components-api.{{ .Release.Namespace }}.svc"
  dnsNames:
    - "components-api.{{ .Release.Namespace }}.svc"
    - "components-api.{{ .Release.Namespace }}.svc.{{ .Values.certificates.internalClusterDomain }}"
  secretName: "{{ .Release.Name }}-certificate"
  usages:
    - server auth
  duration: "504h" # 21d
  privateKey:
    algorithm: ECDSA
    size: 256
  issuerRef: {{ .Values.certificates.apiGatewayCa | toYaml | nindent 4 }}
