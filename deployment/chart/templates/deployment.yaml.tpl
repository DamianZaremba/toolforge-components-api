apiVersion: apps/v1
kind: Deployment
metadata:
  name: components-api
  labels:
    name: components-api
  annotations:
    secret.reloader.stakater.com/reload: "{{ .Release.Name }}-certificate"
spec:
  replicas: {{ .Values.replicas }}
  selector:
    matchLabels:
      name: components-api
  template:
    metadata:
      name: components-api
      labels:
        name: components-api
    spec:
      containers:
        - name: api
          image: "{{ .Values.image.name }}:{{ .Values.image.tag }}"
          imagePullPolicy: "{{ .Values.image.pullPolicy }}"
          env:
            - name: "LOG_LEVEL"
              value: "{{ if .Values.config.debug }}debug{{ else }}info{{ end }}"
            - name: "PORT"
              value: "{{ .Values.config.port }}"
            - name: "STORAGE_TYPE"
              value: "kubernetes"
            - name: "TOOLFORGE_API_URL"
              value: "{{ .Values.config.toolforge_api_url }}"
            - name: "VERIFY_TOOLFORGE_API_CERT"
              value: "{{ .Values.config.verify_toolforge_api_cert }}"
            - name: "MAX_DEPLOYMENTS_RETAINED"
              value: "{{ .Values.config.max_deployments_retained }}"
            - name: "BUILD_TIMEOUT_SECONDS"
              value: "{{ .Values.config.build_timeout_seconds }}"
            - name: "MAX_PARALLEL_DEPLOYMENTS"
              value: "{{ .Values.config.max_parallel_deployments }}"
            - name: "PROMETHEUS_MULTIPROC_DIR"
              value: "/tmp/prometheus"
          resources: {{- toYaml .Values.resources | nindent 12 }}
          securityContext:
            readOnlyRootFilesystem: true
          volumeMounts:
            - mountPath: /etc/components-api
              name: api-gateway-server-cert
              readOnly: true
            - mountPath: /tmp/prometheus
              name: prometheus-multiproc-dir
            - mountPath: /tmp/writable-tmp
              name: writable-tmp-dir
        - name: nginx
          image: "{{ .Values.nginx.image.repository }}:{{ .Values.nginx.image.nginxTag }}"
          imagePullPolicy: Always
          ports:
            - containerPort: 8443
              name: https
              protocol: TCP
            - containerPort: 9000
              name: metrics
              protocol: TCP
          resources: {}
          volumeMounts:
            - mountPath: /etc/nginx/api-gateway-ssl
              name: api-gateway-server-cert
              readOnly: true
            - mountPath: /etc/nginx/nginx.conf
              name: nginx-config
              readOnly: true
              subPath: nginx.conf
          startupProbe:
            failureThreshold: 10
            httpGet:
              path: /v1/healthz
              port: 9000
              scheme: HTTP
            initialDelaySeconds: 1
            periodSeconds: 1
            successThreshold: 1
            timeoutSeconds: 10
          livenessProbe:
            httpGet:
              path: /v1/healthz
              port: 9000
            initialDelaySeconds: 3
            periodSeconds: 3
          securityContext:
            runAsUser: 65534
      serviceAccountName: components-api
      volumes:
        - configMap:
            items:
              - key: nginx.conf
                path: nginx.conf
            name: nginx-config
          name: nginx-config
        - name: api-gateway-server-cert
          secret:
            secretName: "{{ .Release.Name }}-certificate"
        - name: prometheus-multiproc-dir
          emptyDir: {}
        - name: writable-tmp-dir
          emptyDir: {}
