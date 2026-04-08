import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

public class GeneratePassword {
    public static void main(String[] args) {
        BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();
        String password = "admin";
        String encodedPassword = passwordEncoder.encode(password);
        System.out.println("密码 'admin' 的BCrypt哈希值：");
        System.out.println(encodedPassword);
    }
}
