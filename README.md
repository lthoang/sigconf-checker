# sigconf-checker
Inspired by [aclpubcheck](https://github.com/acl-org/aclpubcheck), I adapt the source code to check the ACM `sigconf` format, i.e., paper size (Letter size) and margins (top: 57pt, bottom: 73pt, left: 54pt, right: 54pt).

## Usage

Install required packages:

```bash
pip install -r requirements.txt
```

Run the checking tool:

```bash
python check.py <input file or folder> -o <output dir>
```
