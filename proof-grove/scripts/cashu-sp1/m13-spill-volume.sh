#!/bin/bash
set -Eeuo pipefail

action=${1:?supply a spill volume action}
uuid=${2:?supply the spill volume UUID}
[[ "$uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]
size=17716740096
mount_dir="/var/tmp/cashu-m13-spill-$uuid"
image="/mnt/d/ProofGroveCashuScratch/m13-spill-$uuid.vhdx"

case "$action" in
    prepare)
        [[ ! -e "$image" && ! -L "$image" ]]
        raw=$(mktemp /var/tmp/cashu-m13-spill-image.XXXXXXXX)
        trap 'rm -f -- "$raw"' EXIT
        truncate -s "$size" -- "$raw"
        # Format the private regular image before exposing any block device.
        mkfs.ext4 -q -F -m 0 -T largefile -J size=32 -E nodiscard,lazy_itable_init=0,lazy_journal_init=0 \
            -U "$uuid" "$raw"
        /usr/bin/qemu-img convert -f raw -O vhdx -o block_size=1048576 -S 4096 "$raw" "$image"
        ;;
    mount)
        devices=()
        while read -r candidate bytes kind; do
            if [[ "$kind" == disk && "$bytes" == "$size" && $(blkid -s UUID -o value "$candidate") == "$uuid" ]]; then
                devices+=("$candidate")
            fi
        done < <(lsblk -bdnpo NAME,SIZE,TYPE)
        [[ ${#devices[@]} == 1 ]]
        device=${devices[0]}
        [[ "$device" =~ ^/dev/sd[a-z]+$ && -z $(lsblk -nro MOUNTPOINT "$device") ]]
        mkdir -- "$mount_dir"
        mount -t ext4 -o noatime -- "$device" "$mount_dir"
        available=$(df -PB1 "$mount_dir" | awk 'NR == 2 {print $4}')
        [[ "$available" =~ ^[0-9]+$ ]] && ((available >= 17179869184))
        printf '%s %s %s\n' "$mount_dir" "$device" "$available"
        ;;
    unmount)
        if mountpoint -q "$mount_dir"; then
            device=$(findmnt -n --mountpoint "$mount_dir" -t ext4 -o SOURCE)
            [[ $(blkid -s UUID -o value "$device") == "$uuid" ]]
            umount -- "$mount_dir"
        fi
        if [[ -d "$mount_dir" ]]; then rmdir -- "$mount_dir"; fi
        ;;
    *) exit 2 ;;
esac
