# Saffron

A small native SPICE viewer for KVM/libvirt and Proxmox VMs. It's built on
the SPICE client from [IT Toolbox](https://github.com/ryanvanmass/it-toolbox)
(spice-glib driven from Python, drawn with Qt) and stands in for
`remote-viewer`/`virt-viewer`, which are poorly maintained on macOS.
[virt-connect](https://github.com/ryanvanmass/virt-connect) uses it as its
viewer on the Mac.
