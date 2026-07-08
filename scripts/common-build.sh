#!/bin/bash
set -e

# Args select the site-config env to copy; without this check a bad pair
# would die with an unhelpful cp error under set -e.
if [ $# -ne 2 ] || [ ! -f "./site-config/$1/$2/.env" ]; then
	echo "Usage: $0 <site> <environment> — ./site-config/<site>/<environment>/.env must exist (e.g. $0 ncpi-catalog dev)" >&2
	exit 1
fi

DIR="./site-config/$1/images/favicons/"
PUBLIC_DIR="./public/favicons/"
# init

cp ./site-config/$1/$2/.env .env.production

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