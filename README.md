# Toolforge Components API

This is the Toolforge components-api.

For now, it is just a skeleton FastAPI application.

To deploy it, follow the same pattern as the other Toolforge components
(jobs-api, envvars-api...)

For local development, you can use the following command to start the
application:

```shell
poetry run uvicorn --factory components.main:create_app --reload
```

This will start the application on <http://localhost:8000>.

## API Endpoints

All endpoints are prefixed with `/v1` to ensure versioning of the API.

For detailed information about request and response formats, please refer to the
API documentation or the OpenAPI specification.

## Generating the tool config schema

You can generate the tool config schema from the `openapi.yaml` file by running
the scr `utils/generate_config_schema.py`.

### How to use it

You can now set the schema on your config file, for example, if you use
yaml-language-server, you have to add this line to the top:

```yaml
# yaml-language-server: $schema=https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api/-/raw/main/openapi/tool-config-schema.json
```

## Developing tricks

### Generating the toolforge models

To regenerate the toolforge models you can just run:

```shell
dcaro@lima-kilo$ poetry run datamodel-codegen --url https://api.svc.toolforge.org/openapi.json --output components/gen/toolforge_models.py
```

### Using the kubernetes storage connecting directly to lima-kilo

For this you can start your lima-kilo installation, then copy the `.kube/config`
file locally:

```shell
dcaro@lima-kilo$ cat ~/.kube/config
.... some data, copy-paste to a local file

dcaro@mylaptop$ vim ~/.kube/lima-kilo-config
... paste the data there
```

Create a tunnel to the k8s cluster API (whichever way you prefer, this is just
one of many):

```shell
dcaro@mylaptop$ limactl list
WARN[0000] provisioning scripts should not reference the LIMA_CIDATA variables
NAME         STATUS     SSH                VMTYPE    ARCH      CPUS    MEMORY    DISK      DIR
lima-kilo    Running    127.0.0.1:44417    qemu      x86_64    16      8GiB      100GiB    ~/.lima/lima-kilo
                         ^note this ip/port

dcaro@mylaptop$ ssh -NfL 33785:127.0.0.1:33785 127.0.0.1 -p 44417
# the 33785 port comes from the kubeconfig
```

Then tell the components api where to find the kubeconfig

```shell
dcaro@mylaptop$ env KUBECONFIG=~/.kube/lima-kilo-config STORAGE_TYPE=kubernetes LOG_LEVEL=debug poetry run fastapi run components/main.py
```

### Deploying into lima-kimo

To support running functional tests, it is useful to be able to change the deployed image inside lima-kilo.

* Build the components-api container image
```
lima-kilo:~$ git clone https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api
lima-kilo:~$ cd components-api
lima-kilo:~/components-api$ docker buildx build --target image -f .pipeline/blubber.yaml -t tools-harbor.wmcloud.org/toolforge/components-api:dev .
```

* Load the built container image
```
lima-kilo:~/components-api$ kind load docker-image tools-harbor.wmcloud.org/toolforge/components-api:dev -n toolforge
```

* Deploy to restart the service
```
lima-kilo:~/components-api$ ./deploy.sh local
```

* The API should now be accessible
```
lima-kilo:~/components-api$ kubectl -n components-api get pods
NAME                              READY   STATUS    RESTARTS   AGE
components-api-569b967ffc-hjw2p   1/2     Running   0          8s

lima-kilo:~/components-api$ curl -sk https://localhost:30003/components/v1/healthz | jq .
{
  "data": {
    "status": "OK"
  },
  "messages": {
    "info": [],
    "warning": [
      "You are using a beta feature of Toolforge."
    ],
    "error": []
  }
}
```
