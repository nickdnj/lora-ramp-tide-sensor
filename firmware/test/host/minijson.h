// Minimal JSON reader for the shared test vectors (objects, arrays, strings, numbers,
// true/false/null). Test-only; not used by the firmware.
#pragma once

#include <cstdlib>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace minijson {

struct Value {
  enum Type { Null, Bool, Number, String, Array, Object } type = Null;
  bool b = false;
  double num = 0;
  std::string str;
  std::vector<Value> arr;
  std::vector<std::pair<std::string, Value>> obj;

  const Value& operator[](const std::string& k) const {
    for (const auto& kv : obj)
      if (kv.first == k) return kv.second;
    throw std::runtime_error("missing key: " + k);
  }
  const Value& operator[](size_t i) const { return arr.at(i); }
  bool has(const std::string& k) const {
    for (const auto& kv : obj)
      if (kv.first == k) return true;
    return false;
  }
  bool is_null() const { return type == Null; }
  long long i() const { return static_cast<long long>(num); }
  size_t size() const { return type == Array ? arr.size() : obj.size(); }
};

class Parser {
 public:
  explicit Parser(const std::string& s) : s_(s) {}
  Value parse() {
    Value v = value();
    ws();
    if (p_ != s_.size()) throw std::runtime_error("trailing data");
    return v;
  }

 private:
  const std::string& s_;
  size_t p_ = 0;
  void ws() {
    while (p_ < s_.size() && (s_[p_] == ' ' || s_[p_] == '\n' || s_[p_] == '\r' || s_[p_] == '\t')) ++p_;
  }
  char peek() {
    ws();
    if (p_ >= s_.size()) throw std::runtime_error("unexpected end");
    return s_[p_];
  }
  void expect(char c) {
    if (peek() != c) throw std::runtime_error(std::string("expected ") + c);
    ++p_;
  }
  Value value() {
    char c = peek();
    if (c == '{') return object();
    if (c == '[') return array();
    if (c == '"') {
      Value v;
      v.type = Value::String;
      v.str = string();
      return v;
    }
    if (s_.compare(p_, 4, "true") == 0) { p_ += 4; Value v; v.type = Value::Bool; v.b = true; return v; }
    if (s_.compare(p_, 5, "false") == 0) { p_ += 5; Value v; v.type = Value::Bool; return v; }
    if (s_.compare(p_, 4, "null") == 0) { p_ += 4; return Value(); }
    return number();
  }
  Value number() {
    const char* start = s_.c_str() + p_;
    char* end = nullptr;
    double d = std::strtod(start, &end);
    if (end == start) throw std::runtime_error("bad number");
    p_ += static_cast<size_t>(end - start);
    Value v;
    v.type = Value::Number;
    v.num = d;
    return v;
  }
  std::string string() {
    expect('"');
    std::string out;
    while (p_ < s_.size() && s_[p_] != '"') {
      char c = s_[p_++];
      if (c == '\\') {
        char e = s_[p_++];
        switch (e) {
          case 'n': out += '\n'; break;
          case 't': out += '\t'; break;
          case 'u': out += '?'; p_ += 4; break;  // not needed by our vectors
          default: out += e;
        }
      } else {
        out += c;
      }
    }
    ++p_;
    return out;
  }
  Value array() {
    expect('[');
    Value v;
    v.type = Value::Array;
    if (peek() == ']') { ++p_; return v; }
    for (;;) {
      v.arr.push_back(value());
      if (peek() == ',') { ++p_; continue; }
      expect(']');
      return v;
    }
  }
  Value object() {
    expect('{');
    Value v;
    v.type = Value::Object;
    if (peek() == '}') { ++p_; return v; }
    for (;;) {
      ws();
      std::string k = string();
      expect(':');
      v.obj.emplace_back(k, value());
      if (peek() == ',') { ++p_; continue; }
      expect('}');
      return v;
    }
  }
};

}  // namespace minijson
