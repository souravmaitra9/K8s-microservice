"""Fixed runbooks. There is no write path and no embedding index."""

DOCS: tuple[dict[str, str], ...] = (
    {
        "id": "crashloop",
        "title": "CrashLoopBackOff",
        "body": (
            "Check the previous container exit code and the last 50 log lines. "
            "Exit 137 is an OOM: compare the memory limit with the process RSS. "
            "Exit 1 means startup failed; confirm the config and the downstream dependency. "
            "Do not raise the restart budget to hide a failing probe. "
            "Roll back the deployment if the error started on the current release."
        ),
    },
    {
        "id": "kafka-lag",
        "title": "Kafka consumer lag",
        "body": (
            "Confirm whether the lag is one partition or the whole group. "
            "Look for a stuck consumer, a full broker disk, or a rebalance loop. "
            "Scale the consumer only when handler time is healthy and the lag slope is positive. "
            "Do not reset offsets to latest unless the data loss is accepted."
        ),
    },
    {
        "id": "disk-pressure",
        "title": "Node disk pressure",
        "body": (
            "Eviction is the kubelet's last resort. Find the volume that filled: "
            "container logs, an emptyDir, or an image layer. "
            "Cordon the node before deleting unused images. "
            "If the node root disk is full, replace the node rather than cleaning it in place."
        ),
    },
    {
        "id": "cert-expiry",
        "title": "Ingress certificate expiry",
        "body": (
            "Check the certificate not-after date and the issuer. "
            "A failed renewal is usually a DNS challenge or an expired solver role. "
            "Do not pin an old certificate as a workaround. "
            "After renewal, confirm the served chain from outside the cluster."
        ),
    },
    {
        "id": "oomkilled",
        "title": "OOMKilled",
        "body": (
            "Exit 137 with reason OOMKilled means the cgroup limit was hit, "
            "not that the node ran out of memory. "
            "Compare the limit with the steady RSS and the startup spike. "
            "Raise the limit only when the working set is real. "
            "A leak needs a fix, not an unbounded limit."
        ),
    },
)
