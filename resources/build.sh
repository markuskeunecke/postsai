#!/bin/sh

cd `dirname $0`/..

rm -rf dist
mkdir -p dist/postsai
cp -ax *.html *.js *.md *.py *.txt resources dist/postsai
cp --parents node_modules/bootstrap/dist/css/bootstrap.min.css node_modules/bootstrap/dist/js/bootstrap.min.js                    dist/postsai
cp --parents node_modules/bootstrap/dist/fonts/*                                                          dist/postsai
cp --parents node_modules/bootstrap-table/dist/bootstrap-table.min.css node_modules/bootstrap-table/dist/bootstrap-table.min.js   dist/postsai
cp --parents node_modules/bootstrap-table/dist/extensions/export/bootstrap-table-export.min.js            dist/postsai
cp --parents node_modules/bootstrap-table/dist/extensions/mobile/bootstrap-table-mobile.min.js            dist/postsai
cp --parents node_modules/tableExport.jquery.plugin/tableExport.min.js                                    dist/postsai
cp --parents node_modules/js-md5/build/md5.min.js                                                         dist/postsai
cp --parents node_modules/jquery/dist/jquery.min.js                                                       dist/postsai
cp --parents node_modules/highlightjs/styles/default.css node_modules/highlightjs/highlight.pack.min.js   dist/postsai
rm dist/postsai/config.py*
cd dist
zip -r postsai-$npm_package_version.zip postsai



