---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: "components-api-certificate"
  labels:
    name: "components-api"
spec:
  commonName: "service:components-api"
  dnsNames:
    - "components-api.{{ .Release.Namespace }}.svc"
    - "components-api.{{ .Release.Namespace }}.svc.{{ .Values.certificates.internalClusterDomain }}"
  secretName: "{{ .Release.Name }}-certificate"
  subject:
    organizations:
      - toolforge
  usages:
    - server auth
    - client auth
  duration: "504h" # 21d
  privateKey:
    algorithm: ECDSA
    size: 256
  issuerRef: {{ .Values.certificates.apiGatewayCa | toYaml | nindent 4 }}
