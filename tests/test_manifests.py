"""Parser tests for the supported dependency manifests."""

from __future__ import annotations

from textwrap import dedent

import pytest

from radar.signals.manifests import (
    cargo_toml,
    composer,
    gemfile,
    go_mod,
    gradle,
    mix,
    pom,
    pubspec,
    pyproject,
)


def test_pyproject_reads_pep508_poetry_and_dependency_groups():
    text = dedent(
        """\
        [project]
        name = "demo"
        dependencies = [
          "Requests[security] >= 2.8.1; python_version < '3.11'",
          "python_dateutil>=2.8",
          "pkg @ https://example.invalid/pkg.whl",
        ]

        [project.optional-dependencies]
        dev = ["pytest>=7", "pytest-cov ; extra == 'test'"]
        docs = ["Sphinx (>=5)"]

        [tool.poetry]
        name = "demo"

        [tool.poetry.dependencies]
        python = "^3.9"
        Django = "^4.2"
        my_pkg = { version = "^1.0", extras = ["security"] }

        [tool.poetry.group.dev.dependencies]
        python = "^3.9"
        black = "^23.0"

        [tool.poetry.group.test.dependencies]
        pytest = "^7.0"

        [dependency-groups]
        test = ["coverage[toml]>=6", {include-group = "dev"}]
        """
    )

    assert pyproject.parse(text) == {
        "requests",
        "python-dateutil",
        "pkg",
        "pytest",
        "pytest-cov",
        "sphinx",
        "django",
        "my-pkg",
        "black",
        "coverage",
    }


def test_go_mod_reads_single_and_block_require_and_skips_indirect():
    text = dedent(
        """\
        module example.com/demo

        go 1.22
        toolchain go1.22.0

        require github.com/stretchr/testify v1.9.0
        require golang.org/x/sync v0.7.0 // indirect

        require (
            github.com/gin-gonic/gin v1.10.0
            github.com/spf13/cobra v1.8.0 // indirect
            golang.org/x/text v0.15.0
        )

        replace github.com/old/module => github.com/new/module v1.2.3
        exclude github.com/bad/module v1.0.0
        """
    )

    assert go_mod.parse(text) == {
        "github.com/stretchr/testify",
        "github.com/gin-gonic/gin",
        "golang.org/x/text",
    }


def test_cargo_toml_reads_tables_and_renamed_packages():
    text = dedent(
        """\
        [package]
        name = "demo"
        version = "0.1.0"

        [dependencies]
        serde = { version = "1", features = ["derive"] }
        renamed = { package = "real-crate", version = "2" }
        tokio = "1"

        [dev-dependencies]
        tempfile = "3"

        [build-dependencies]
        cc = "1"

        [workspace.dependencies]
        anyhow = "1"

        [target.'cfg(unix)'.dependencies]
        nix = "0.29"
        """
    )

    assert cargo_toml.parse(text) == {
        "serde",
        "real-crate",
        "tokio",
        "tempfile",
        "cc",
        "anyhow",
        "nix",
    }


def test_gemfile_reads_gem_lines_and_ignores_comments():
    text = dedent(
        """\
        source "https://rubygems.org"

        gem "rails", "~> 7.1"
        gem 'pg', '~> 1.5'
        # gem "commented", "1.0"

        group :development, :test do
          gem "rspec-rails", require: false
          gem 'pry', git: "https://example.invalid/pry.git"
        end
        """
    )

    assert gemfile.parse(text) == {"rails", "pg", "rspec-rails", "pry"}


def test_composer_reads_require_and_require_dev_and_skips_platform_packages():
    text = dedent(
        """\
        {
          "require": {
            "php": ">=8.1",
            "ext-json": "*",
            "lib-icu": "*",
            "monolog/monolog": "^3.0",
            "symfony/console": "^6.4"
          },
          "require-dev": {
            "phpunit/phpunit": "^10.0"
          }
        }
        """
    )

    assert composer.parse(text) == {
        "monolog/monolog",
        "symfony/console",
        "phpunit/phpunit",
    }


def test_pom_reads_namespaced_and_managed_dependencies_and_skips_plugins():
    text = dedent(
        """\
        <project xmlns="http://maven.apache.org/POM/4.0.0">
          <modelVersion>4.0.0</modelVersion>
          <dependencies>
            <dependency>
              <groupId>org.springframework</groupId>
              <artifactId>spring-core</artifactId>
              <version>${spring.version}</version>
            </dependency>
          </dependencies>
          <dependencyManagement>
            <dependencies>
              <dependency>
                <groupId>com.fasterxml.jackson.core</groupId>
                <artifactId>jackson-databind</artifactId>
                <version>${jackson.version}</version>
              </dependency>
              <dependency>
                <groupId>${project.groupId}</groupId>
                <artifactId>placeholder-lib</artifactId>
              </dependency>
            </dependencies>
          </dependencyManagement>
          <build>
            <plugins>
              <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <dependencies>
                  <dependency>
                    <groupId>org.example</groupId>
                    <artifactId>plugin-helper</artifactId>
                  </dependency>
                </dependencies>
              </plugin>
            </plugins>
          </build>
        </project>
        """
    )

    assert pom.parse(text) == {
        "org.springframework:spring-core",
        "com.fasterxml.jackson.core:jackson-databind",
        "${project.groupId}:placeholder-lib",
    }


def test_gradle_reads_groovy_and_kotlin_dsl_forms():
    text = dedent(
        """\
        plugins { id 'java' }

        dependencies {
            implementation 'org.springframework:spring-core:6.1.0'
            implementation("com.google.guava:guava:33.0.0-jre")
            api project(':shared')
            testImplementation("org.junit.jupiter:junit-jupiter:5.10.0")
            testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
            compileOnly "org.projectlombok:lombok:1.18.30"
            runtimeOnly('org.postgresql:postgresql:42.7.0')
            kapt "com.google.dagger:dagger-compiler:2.50"
            annotationProcessor("com.google.auto.value:auto-value:1.10.4")
            implementation files('libs/local.jar')
            implementation project(path: ':other')
            // implementation 'commented:out:1.0'
            /* implementation 'block:commented:2.0' */
        }
        """
    )

    assert gradle.parse(text) == {
        "org.springframework:spring-core",
        "com.google.guava:guava",
        "org.junit.jupiter:junit-jupiter",
        "org.junit.platform:junit-platform-launcher",
        "org.projectlombok:lombok",
        "org.postgresql:postgresql",
        "com.google.dagger:dagger-compiler",
        "com.google.auto.value:auto-value",
    }


def test_pubspec_reads_two_space_children_and_skips_sdk_dependencies():
    text = dedent(
        """\
        name: demo
        description: A demo app.

        environment:
          sdk: ">=3.0.0 <4.0.0"

        dependencies:
          flutter:
            sdk: flutter
          cupertino_icons: ^1.0.6
          http: ^1.2.0
          path:
            git:
              url: https://example.invalid/path.git
              ref: main
          local_pkg:
            sdk: flutter
          another_local:
            path: ../another_local
          commented: # the comment is not part of the name
            version: ^1.0.0

        dev_dependencies:
          flutter_test:
            sdk: flutter
          build_runner: ^2.4.0
          integration_test:
            sdk: flutter
        """
    )

    assert pubspec.parse(text) == {
        "cupertino_icons",
        "http",
        "path",
        "another_local",
        "commented",
        "build_runner",
    }


def test_mix_reads_version_and_github_dependencies():
    text = dedent(
        """\
        defmodule Demo.MixProject do
          use Mix.Project

          defp deps do
            [
              {:phoenix, "~> 1.7.0"},
              {:phoenix_html, "~> 4.0"},
              {:jason, "~> 1.4"},
              {:my_dep, github: "owner/my_dep"},
              {:ex_doc, "~> 0.31", only: :dev, runtime: false},
              {:local_dep, path: "../local_dep"},
              {:hex_dep, hex: :hex_dep},
              {:multiline_dep,
                "~> 2.0"},
              # {:commented, "~> 1.0"},
              {:ok, pid}
            ]
          end
        end
        """
    )

    assert mix.parse(text) == {
        "phoenix",
        "phoenix_html",
        "jason",
        "my_dep",
        "ex_doc",
        "local_dep",
        "hex_dep",
        "multiline_dep",
    }


@pytest.mark.parametrize(
    "parser",
    [
        pyproject.parse,
        go_mod.parse,
        cargo_toml.parse,
        gemfile.parse,
        composer.parse,
        pom.parse,
        gradle.parse,
        pubspec.parse,
        mix.parse,
    ],
)
@pytest.mark.parametrize("text", ["", "   \n", "not a manifest"])
def test_manifest_parsers_return_empty_sets_on_invalid_input(parser, text):
    assert parser(text) == set()
