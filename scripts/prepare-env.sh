#!/bin/bash
set -e

# Copies the site-config env into the given dotenv file (.env.development for
# `next dev`, .env.production for `next build`) and stages favicons.
if [ $# -ne 3 ] || [ ! -f "./site-config/$1/$2/.env" ]; then
	echo "Usage: $0 <site> <environment> <target-env-file> — ./site-config/<site>/<environment>/.env must exist (e.g. $0 ncpi-catalog dev .env.production)" >&2
	exit 1
fi

DIR="./site-config/$1/images/favicons/"
PUBLIC_DIR="./public/favicons/"

cp "./site-config/$1/$2/.env" "$3"

# check if PUBLIC_DIR does not exists
if [ ! -d "$PUBLIC_DIR" ]; then
	mkdir $PUBLIC_DIR
fi

# look for empty directory
if [ -d "$DIR" ]
then
	if [ "$(ls $DIR)" ]; then
     cp ./site-config/$1/images/favicons/* ./public/favicons/
	 cp ./scripts/browserconfig.xml ./public/favicons/
	 cp ./scripts/site.webmanifest ./public/favicons/
	fi
else
	echo "Directory $DIR not found."
fi
