#!/bin/sh
set -eo pipefail
IFS=$'\n\t'
BASE_URL='https://ftp.ncbi.nlm.nih.gov/geo/series/'
DATASET_URL='https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc='
UNPACK=false
URL_FILE=false
FILENAME=''
GEO_CODE=''
FOLDER_NAME=''

download_from_file() {
  inp_file="$1"
  target_folder="$2"
  echo "Try to get files from $inp_file by ID..."
  if [ -z "$2" ] ; then
    echo "NO TARGET FOLDER...Using Id names instead."
  fi
  while IFS="" read -r p || [ -n "$p" ]
  do
    download_geo_code "$p" "$target_folder"
  done < "$inp_file"
}

write_url_to_file() {
  > url_file.txt
  if [ -z "$FILENAME" ]; then
    echo "${DATASET_URL}${GEO_CODE}" >> url_file.txt
  else
    while IFS="" read -r p || [ -n "$p" ]
    do
      echo "${DATASET_URL}${p}" >> url_file.txt
    done < "$FILENAME"
  fi
}

download_geo_code() {
  inp_code="$1"
  if [ -z "$2" ] ; then
    FOLDER_NAME="${PWD}/${inp_code}"
    echo "NO TARGET FOLDER...Using $FOLDER_NAME instead."
  else
    target_folder="$2"
    echo "$target_folder"
  fi
  echo "Create target folder..."
  [ -d "$FOLDER_NAME" ] || mkdir -p "$FOLDER_NAME"

  # build download url
  code_number=$(echo "$inp_code" | sed -e 's/...$/nnn/g')
 
  # Änderung 6.5 soft.gz statt cel
  target_file="${inp_code}_family.soft.gz"

  # Änderung 6.5 richtiger Pfad
  target_url="${BASE_URL}${code_number}/${inp_code}/soft/${target_file}"

  if test -f "$FOLDER_NAME/${target_file}"; then
    echo "File exists, not downloading!"
  else
    wget -nc -O "${FOLDER_NAME}/${target_file}" "$target_url"
  fi
}

# Unpack_geo_files wurde gelöscht, da GEOparse die Dateien direkt aus dem Archiv lesen kann
unpack_geo_files() {
  if [ -z "$FOLDER_NAME" ]; then
    echo "No input folder provided!"
    exit 1
  else
    echo "Try Unpacking geo files in ${FOLDER_NAME}/..."
    echo "Try to unpack all gz archives..."
    gz_files=($(find "${FOLDER_NAME}/" -maxdepth 1 -name "*_family.soft.gz"))
    echo ${gz_files}
    if [ ${#gz_files[@]} -gt 0 ]; then
      for i in "${gz_files[@]}"; do
        [ -f "$i" ] || break
        echo "Unpacking file: $i"
        gunzip -c "$i" > "${FOLDER_NAME}/$(basename "$i" .gz)"
        rm "$i"
        echo "Compressed file deleted."
      done
    else
      echo "No gz data files found!"
    fi
    echo "Try to unpack all gz files..."
    cel_files=($(find "${FOLDER_NAME}/" -maxdepth 1 -name "*_family.soft.gz"))
    if [ ${#cel_files[@]} -gt 0 ]; then
      for i in "${cel_files[@]}"; do
        [ -f "$i" ] || break
        echo "$i"
        base_name=$(basename "${i}" .gz)
        gunzip -c "$i" > "${FOLDER_NAME}/${base_name}"
        rm "$i"
      done
    else
      echo "No gz data files found!"
    fi
    echo "File unpacking done!"
    echo "========================================="
  fi
}

usage() {
  echo "scrape_data.sh [-u] [-f filename | -c geo dataset id] [-d output folder name]"
  echo "-u: unpack files "
  exit 1
}


while getopts hulf:c:d: opt
do
  case $opt in
    u)
    UNPACK=true
    ;;
    l)
      URL_FILE=true
      ;;
    f)
      inp_file=${OPTARG}
      FILENAME="$inp_file"
      ;;
    c)
      geo_code=${OPTARG}
      GEO_CODE="$geo_code"
      ;;
    d)
      folder_name=${OPTARG}
      FOLDER_NAME="$folder_name"
      ;;
    h | *)
      usage
      ;;
  esac
done

if [ $# -eq 0 ]; then
  usage
else
  if [ -z "$FILENAME" ]; then
    echo "Try to download geo id $GEO_CODE..."
    download_geo_code $GEO_CODE $FOLDER_NAME
  else
    echo "Try to download geo datasets from file $FILENAME"
    download_from_file $FILENAME $FOLDER_NAME
  fi
  if [ "$UNPACK" = true ]; then
    unpack_geo_files
  fi
  if [ "$URL_FILE" = true ]; then
    write_url_to_file
  fi
fi
