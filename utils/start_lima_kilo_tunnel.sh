#!/bin/bash
set -o nounset
set -o errexit
set -o pipefail

K8S_TUNNEL_PORT="${K8S_TUNNEL_PORT:-1234}"
TOOLFORGE_TUNNEL_PORT="${TOOLFORGE_TUNNEL_PORT:-30003}"

main() {
    local ssh_hostport \
        ssh_port \
        ssh_host \
        k8s_port

    if ! limactl list | grep -q lima-kilo; then
        echo "Unable to find lima-kilo, make sure it's running"
        exit 2
    fi

    ssh_hostport=$(limactl list | grep lima-kilo | awk '{print $3}')
    ssh_host=${ssh_hostport%%:*}
    ssh_port=${ssh_hostport##*:}

    echo "Copying the certificates from lima-kilo"
    scp -P "$ssh_port" "$ssh_host:.kube/config" ~/.kube/lima-kilo.config
    k8s_port="$(grep server ~/.kube/lima-kilo.config | cut -d: -f4)"
    sed -i ~/.kube/lima-kilo.config -e "s/$k8s_port/$K8S_TUNNEL_PORT/"
    sed -i ~/.kube/lima-kilo.config -e "s/cluster:.*kind-toolforge/cluster: kind-toolforge\n    namespace: default/"

    echo "Starting tunnel from 127.0.0.1:$K8S_TUNNEL_PORT"
    ssh -L "127.0.0.1:$K8S_TUNNEL_PORT:127.0.0.1:$k8s_port" -Nf "$ssh_host" -p "$ssh_port"
    echo "Starting toolforge api tunnel from 127.0.0.1:$TOOLFORGE_TUNNEL_PORT"
    ssh -L "127.0.0.1:$TOOLFORGE_TUNNEL_PORT:127.0.0.1:$TOOLFORGE_TUNNEL_PORT" -Nf "$ssh_host" -p "$ssh_port"

    cat <<EOH
    You can now use:
        env KUBECONFIG=~/.kube/lima-kilo.config kubectl ...

    And similar commands to connect to lima-kilo.
    Enjoy!
EOH
}

main "$@"
