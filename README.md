# openstack-dns-updater

OpenStack DNS Updater listens on the RabbitMQ message bus. Whenever an
instance is created or deleted DNS updater creates or removes
its DNS A record. The name of the instance is directly used as its FQDN.
Hence instances in OpenStack should be named with their FQDN.
The IP address stored in DNS is the IP address of the first network interface
on the private network. You can easily change the script to store floating
IP address in DNS instead.

OpenStack DNS Updater works well on Debian 9.

For more information refer to:
http://alesnosek.com/blog/2015/05/31/openstack-dynamic-dns-updates/
