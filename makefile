default:
	@cat makefile

grab:
	mv ~/Downloads/lcars-flask-monolith-* .

unpack:
	unzip -o lcars-flask-monolith-v${VERSION}.zip
	git checkout *.json

up:
	. ~/.efenv/bin/activate; python app.py
