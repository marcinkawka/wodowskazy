#!/bin/bash

INCOMING_DIR="$(dirname "$0")/../incoming_data"
EXTRACTED_DIR="$(dirname "$0")/../extracted_data"

INCOMING_DIR="$(realpath "$INCOMING_DIR")"
EXTRACTED_DIR="$(realpath "$EXTRACTED_DIR")"

total=0
extracted=0
skipped=0

while IFS= read -r -d '' zip_file; do
    rel_dir="${zip_file#"$INCOMING_DIR"/}"
    rel_dir="$(dirname "$rel_dir")"
    dest_dir="$EXTRACTED_DIR/$rel_dir"

    mkdir -p "$dest_dir"

    unzip -n -q "$zip_file" -d "$dest_dir"
    status=$?

    total=$((total + 1))
    if [ $status -eq 0 ]; then
        extracted=$((extracted + 1))
    else
        echo "ERROR: failed to extract $zip_file" >&2
        skipped=$((skipped + 1))
    fi
done < <(find "$INCOMING_DIR" -name "*.zip" -print0 | sort -z)

echo "Done: $extracted extracted, $skipped errors, $total total."
