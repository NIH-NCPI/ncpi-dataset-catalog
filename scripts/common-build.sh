#!/bin/bash

DIR="./site-config/$1/images/favicons/"
PUBLIC_DIR="./public/favicons/"
# init

# Local env overrides must not ship in a build artifact — `next build` loads
# .env.local / .env.*.local (#403; see README "Local backend override").
for f in .env.local .env.*.local; do
	if [ -f "$f" ]; then
		echo "Error: $f would leak into the build. Remove it (use 'npm run dev:local-api' to point dev at a local backend)." >&2
		exit 1
	fi
done

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