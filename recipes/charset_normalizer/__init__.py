from pythonforandroid.recipe import PythonRecipe

class CharsetNormalizerRecipe(PythonRecipe):
    version = '2.1.1'   # 您可以更改为任何需要的版本
    url = 'https://files.pythonhosted.org/packages/source/c/charset_normalizer/charset_normalizer-{version}.tar.gz'
    depends = ['python3']
    # 该包是纯 Python，无需额外编译

recipe = CharsetNormalizerRecipe()
