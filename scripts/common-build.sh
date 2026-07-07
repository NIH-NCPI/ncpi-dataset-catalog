#!/bin/bash
set -e

DIR="./site-config/$1/images/favicons/"
PUBLIC_DIR="./public/favicons/"
# init

# Local env overrides must not ship in a build artifact — `next build` loads
# .env.local / .env.*.local (#403; see README "Local backend override").
for f in .env.local .env.*.local; do
	if [ -f "$f" ]; then
		echo "Error: $f would leak into the build. Remove it (use 'npm run dev:local' to point dev at a local backend)." >&2
		exit 1
	fi
done

# Root .env is also loaded by `next build`. It legitimately holds build-tool
# secrets (never inlined), but NEXT_PUBLIC_* vars in it WOULD be inlined into
# the client bundle — refuse those (#403).
if [ -f .env ] && grep -Eq '^[[:space:]]*(export[[:space:]]+)?NEXT_PUBLIC_' .env; then
	echo "Error: .env contains NEXT_PUBLIC_* vars that would leak into the build. Move them to site-config/ or remove them." >&2
	exit 1
fi

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