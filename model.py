import json as jsonlib
import os
from os import path
from os import system
from os import walk
import filechanges
import datetime
import hashlib
from article import Article
import article


def display(text):
	print(text)



class ArticleReader:
	def __init__(self, filemgr):
		self.filemgr = filemgr

	def read_article(self, name):
		source_markdown = ""
		source_json = ""

		source_lines = self.filemgr.get_source_content(self.filemgr.create_article_file(name))
		if len(source_lines) == 0:
			return Article("None", [], [], "", "", "")

		is_font_matter = False
		open_count = 0
		close_count = 0
		for line in source_lines:
			for c in line:
				if c == '{':
					open_count = open_count + 1
					if is_font_matter == False and open_count == 1:
						is_font_matter = True

				if c == '}':
					open_count = open_count - 1

				if is_font_matter:
					source_json = source_json + c
				else:
					source_markdown = source_markdown + c

				if is_font_matter and open_count == 0:
					is_font_matter = False

		json = jsonlib.loads(source_json)
		return Article(json['Title'], json['Parents'], json['Children'], json['Date'], json['Abstract'], source_markdown)

	def get_frontmatter_json(self, article):
		s = '","'
		return '{\n' \
		+ '"Title": "' + article.title + '",\n' \
		+ '"Abstract": "' + article.abstract + '", \n' \
		+ '"Parents": ["' + s.join([p for p in article.parents]) + '"], \n' \
		+ '"Children": ["' + s.join([c for c in article.children]) + '"], \n' \
		+ '"Date": "' + article.publication_date + '" \n' \
		+ '}'

	def save_article(self, article):
		content = self.get_frontmatter_json(article) + "\n" + article.content
		self.filemgr.set_source_content(article.title, content)

class FileManager:
	def __init__(self, inputFolder, outputFolder, templatesFolder):
		self.source_folder = inputFolder
		self.source_extension = ".md"
		self.template_location = templatesFolder
		self.render_folder = outputFolder
		self.render_extension = ".html"
		self.template_name = "page_template.html"
		self.template_map = "map_template.html"
		self.template_news = "news_template.html"

		# Generate unique name based on outputFolder to register the file changes
		if not path.isdir(".build"):
			os.mkdir(".build")
		db_hash = hashlib.md5(outputFolder.encode('utf-8')).hexdigest()
		db_persistence = filechanges.FileStateDatabasePersistence(".build/" + str(db_hash))
		db = filechanges.FileStateDatabase(db_persistence)
		self.state_monitor = filechanges.FileStateMonitor(db, outputFolder)
		self.file_filters = [".DS_Store"]

	def create_article_file(self, name):
		source = os.path.join(self.source_folder, name + self.source_extension)
		output = os.path.join(self.render_folder, name + self.render_extension)
		return article.ArticleFile(name, source, output)

	def create_template_file(self, name, template_path):
		source = os.path.join(self.template_location, template_path)
		output = os.path.join(self.render_folder, name + self.render_extension)
		file = article.ArticleFile(name, source, output)
		file.is_template = True
		return file

	def apply_filter(self, source_file):
		for filt in self.file_filters:
			if filt in source_file:
				return False
		return True

	def list_source(self):
		raw_source_files = []
		for (dirpath, dirnames, filenames) in walk(self.source_folder):
			raw_source_files.extend(filenames)

		files = []
		for f in raw_source_files:
			if self.apply_filter(self.source_folder + f):
				files.append(self.create_article_file(f[:-len(self.source_extension)]))

		return files

	def list_changed_source(self):
		return self.state_monitor.get_changed_files(self.list_source())

	def exists(self, name):
		return path.exists(os.path.join(self.source_folder, name + self.source_extension))

	def get_source_content(self, file):
		if not path.exists(file.source):
			return ['']
		with open(file.source, "r") as file:
			return file.readlines()

	def set_source_content(self, file, content):
		with open(file.source, "w") as file:
			file.write(content)

	def save_output(self, file, content):
		with open(file.output, "w") as f:
			f.write(content)
		self.state_monitor.update(file)
	
	def delete_article(self, file):
		if os.path.isfile(file.output):
			os.remove(file.output)
		self.state_monitor.remove(file)






# The SourceLinker class handles the creation of new child source files
# as well as checks and updates the links between articles to keep them up-to-date.
class FileLinker:
	def __init__(self, filemgr, article_reader):
		self.filemgr = filemgr
		self.article_reader = article_reader
		self.open_editor_on_create = True

	def create_empty_source_file(self, title, parents):
		d = datetime.date.today().strftime("%Y-%m-%d")
		article = Article(title, parents, [], d, '# ' + title, '')
		self.article_reader.save_article(article)

	def open_editor(self, title):
		filename = self.filemgr.get_full_path(title)
		system('subl "' + filename + '"')

	# Create new, missing files
	def create_new_files(self):
		display("Scanning for new children...")
		new_articles = []
		for file in self.filemgr.list_source():
			article = self.article_reader.read_article(file.name)
			for child_title in article.children:
				if child_title == "":
					continue
				if not self.filemgr.exists(child_title):
					self.create_empty_source_file(child_title, [file.name])
					new_articles.append(child_title)
					display('- Created new children: ' + child_title)
			if len(article.parents) == 0:
				continue
			for parent_title in article.parents:
				if parent_title == '':
					continue
				if not self.filemgr.exists(parent_title):
					self.create_empty_source_file(parent_title, [])
					new_articles.append(parent_title)
					display('- Created new parent: ' + parent_title)

		if self.open_editor_on_create:
			if len(new_articles) != 0:
				display('Opening new files...')
			for article in new_articles:
				self.open_editor(article)


	def update_missing_links(self):
		self.update_parents()
		self.update_children()

	# Updates missing parents
	def update_parents(self):
		display("Updating missing parents...")
		for file in self.filemgr.list_source():
			article = self.article_reader.read_article(file.name)
			for child_title in article.children:
				if child_title == '':
					continue
				child = self.article_reader.read_article(child_title)
				if not file.name in child.parents:
					child.parents.append(file.name)
					self.article_reader.save_article(child)
					display('- Updated ' + child.title + ' with missing parent: ' + file.name)

	# Updates missing children
	def update_children(self):
		display("Updating missing children...")
		for file in self.filemgr.list_source():
			article = self.article_reader.read_article(file.name)
			for parent_title in article.parents:
				if parent_title == '':
					continue

				parent = self.article_reader.read_article(parent_title)
				if not file.name in parent.children:
					parent.children.append(file.name)
					self.article_reader.save_article(parent)
					display('- Updated ' + parent.title + ' with missing children: ' + file.name)